# -*- coding: utf-8 -*-

import werkzeug

from openerp import SUPERUSER_ID
from openerp import http
from openerp.http import request
from openerp.tools.translate import _
from openerp.addons.website.models.website import slug
from openerp.addons.web.controllers.main import login_redirect
from openerp.addons.website_sale.controllers.main import website_sale
from openerp.addons.payment_authorize_cim.lib import authorize
from openerp.addons.payment_authorize_cim.lib.authorize.exceptions import AuthorizeInvalidError

import pprint
import logging
import urlparse
import json
import datetime

_logger = logging.getLogger(__name__)

def init_cim():
      cr, uid, context, registry = request.cr, request.uid, request.context, request.registry
      
      # CIM credentials
      acquirer_obj = request.registry.get('payment.acquirer')
      ids = acquirer_obj.search(cr, SUPERUSER_ID, [('provider', '=', 'authorize_cim')])
      results = acquirer_obj.browse(cr, SUPERUSER_ID, ids)

      if(results.environment == 'test'):
        environment = authorize.Environment.TEST
      else:
        environment = authorize.Environment.PRODUCTION

      authorize.Configuration.configure(
         environment,
         results.authorize_login,
         results.authorize_transaction_key,
       )

class AuthorizeCimController(website_sale):

#validate payment request
    @http.route([
        '/cim_payment/validate',
    ], type='http', auth='user')
    def validate_payment_request(self, **post):
      cr, uid, context, registry = request.cr, request.uid, request.context, request.registry
      credit_card_obj = registry.get('payment_authorize.credit_card_info');

      card_id = request.session.get('selected_card', '')
      
      if not card_id:
        card_id = credit_card_obj.search(cr, SUPERUSER_ID, [('is_default', '=', '1'), ('create_uid', '=', uid)], context=context)
      else:
        card_id = credit_card_obj.search(cr, SUPERUSER_ID, [('id', '=', card_id), ('create_uid', '=', uid)], context=context)

      card_data = credit_card_obj.browse(cr, SUPERUSER_ID, card_id)
      
      if not card_data:
        return json.dumps({'error': 'Please select a card.'})
      else:
        return json.dumps({'success': 'Card valid.'})

#process payment
    @http.route([
        '/payment/process/',
    ], type='http', auth='user')
    def authorize_payment_process(self, **post):
      cr, uid, context, registry = request.cr, request.uid, request.context, request.registry
      
      init_cim()

      tx_id = request.session.get('sale_transaction_id')
      
      address_obj = registry.get('payment_authorize.checkout_address');
      credit_card_obj = registry.get('payment_authorize.credit_card_info');
      
#gather card info
      card_id = request.session.get('selected_card', '')
      if not card_id:
        card_id = credit_card_obj.search(cr, SUPERUSER_ID, [('is_default', '=', '1'), ('create_uid', '=', uid)], context=context)
      else:
        card_id = credit_card_obj.search(cr, SUPERUSER_ID, [('id', '=', card_id), ('create_uid', '=', uid)], context=context)

      card_data = credit_card_obj.browse(cr, SUPERUSER_ID, card_id)
      CIM_card_id = card_data.CIM_card_id
        

#gather shipping info
      shipping_id = request.session.get('shipping', '0')
      if shipping_id == '0':
        shipping_id = address_obj.search(cr, SUPERUSER_ID, [('is_default', '=', '1'), ('address_type', '=', 'shipping'), ('create_uid', '=', uid)], context=context)
      else:
        shipping_id = address_obj.search(cr, SUPERUSER_ID, [('id', '=', shipping_id), ('create_uid', '=', uid)], context=context)

      CIM_shipping_id = address_obj.browse(cr, SUPERUSER_ID, shipping_id).CIM_shipping_id

#gather billing info
      billing_id = request.session.get('billing', '0')
      if billing_id == '0':
        billing_id = address_obj.search(cr, SUPERUSER_ID, [('is_default', '=', '1'), ('address_type', '=', 'billing'), ('create_uid', '=', uid)], context=context)
      else:
        billing_id = address_obj.search(cr, SUPERUSER_ID, [('id', '=', billing_id), ('create_uid', '=', uid)], context=context)

      billing = address_obj.browse(cr, SUPERUSER_ID, billing_id)
      
      #redirect if there is no card or shipping address selected
      if not CIM_card_id or not CIM_shipping_id:
       request.session['card_message'] = 'Please Select a card'
       return werkzeug.utils.redirect('/shop/payment')

      card_details = authorize.CreditCard.details(get_customer_cim_profile_id(), CIM_card_id)
      
      
      authorize.CreditCard.update(get_customer_cim_profile_id(), CIM_card_id, {
        'customer_type': card_details.payment_profile.customer_type,
        'card_number': card_details.payment_profile.payment.credit_card.card_number,
        'expiration_month': card_data.month,
        'expiration_year': card_data.year,
        'billing': {
            'first_name': get_customer_name(),
            'address': str(billing.address1) +' '+ str(billing.address2),
            'city': billing.address_city,
            'state': billing.address_state,
            'zip': billing.address_zip,
            'country': get_country_from_id(billing.address_country.id)
        },
      })

#process the transaction
      try:
        result = authorize.Transaction.sale({
                    'amount': post['x_amount'],
                    'customer_id': get_customer_cim_profile_id(),
                    'payment_id': CIM_card_id,
                    'address_id': CIM_shipping_id,
                    'order': {
                      'invoice_number': post['x_invoice_num'],
                    }
                 })
        tx_obj = registry.get('payment.transaction')
        tx_ids = tx_obj.search(cr, SUPERUSER_ID, [('id', '=', tx_id)])

        #successful transaction
        if result.transaction_response.trans_id:
          tx_obj.write(cr, SUPERUSER_ID, tx_ids, {'authorize_txnid': result.transaction_response.trans_id, 'state': 'done'})

        request.registry['payment.transaction'].form_feedback(cr, SUPERUSER_ID, result.transaction_response, 'Authorize.net CIM', context=context) 

      except:
        pass

      #return result.transaction_response.trans_id + '**' + str(tx_id)
      return werkzeug.utils.redirect('/shop/payment/validate')

# New Checkout Page
    @http.route(auth='user')
    def checkout(self, **post):
      cr, uid, context, registry = request.cr, request.uid, request.context, request.registry
      

      #setup session fields
      if('billing' in request.session):
        pass
      else:
        request.session['billing'] = '0'

      if('shipping' in request.session):
        pass
      else:
        request.session['shipping'] = '0'
      #session fields set

      address_obj = request.session.model('payment_authorize.checkout_address')

      orm_country = registry.get('res.country')
      state_orm = registry.get('res.country.state')

      country_ids = orm_country.search(cr, SUPERUSER_ID, [], context=context)
      countries = orm_country.browse(cr, SUPERUSER_ID, country_ids, context)
      states_ids = state_orm.search(cr, SUPERUSER_ID, [], context=context)
      states = state_orm.browse(cr, SUPERUSER_ID, states_ids, context)

      result_ids = address_obj.search([('address_type', '=', 'billing'), ('create_uid', '=', uid)])
      addresses_billing = address_obj.browse(result_ids)
      
      result_ids = address_obj.search([('address_type', '=', 'shipping'), ('create_uid', '=', uid)])
      addresses_shipping = address_obj.browse(result_ids)

      message = ''
      if 'checkout_message' in request.session:
        message = request.session['checkout_message']
        del request.session['checkout_message']

      return request.website.render('payment_authorize_cim.checkout_page_template', {'addresses_billing': addresses_billing, 'addresses_shipping': addresses_shipping, 'countries': countries, 'states': states, 'request': request, 'message': message})

# Adding billing and shipping address to the db
    @http.route([
        '/shop/address/submit/'
    ], type='http', auth='user', website=True)
    def save_address(self, **post):
      cr, uid, context, registry = request.cr, request.uid, request.context, request.registry
      
      init_cim()
      
      if post:
        
        address_obj = registry.get('payment_authorize.checkout_address')
        
        errors = self.validate_form(post)
        if errors:
          return json.dumps(errors)

        # if there is no address_id then create new record, else update
        status = ''
        if post['address_id'] == '':
          
          # setup first entry to be default one
          obj_count = address_obj.search_count(cr, SUPERUSER_ID, [('address_type', '=', post['address_type']), ('create_uid', '=', uid)])
          if obj_count > 0:
            is_default = 0
          else:
            is_default = 1

          #setup CIM user profile if one does not exist
          CIM_profile_id = cim_profile_exists()
          
          if not CIM_profile_id:
            CIM_profile_id = setup_cim_profile()
            
          #store shipping address in CIM
          address_id = 0
          if post['address_type'] == 'shipping':
            address = authorize.Address.create(str(CIM_profile_id), {
                  'first_name': get_customer_name(),
                  'last_name': '',
                  'address': post['address1'] + ' '+ post['address2'],
                  'city': post['city'],
                  'state': post['state'],
                  'zip': post['zipcode'],
                  'country': get_country_from_id(post['country'])
            })
            address_id = address.address_id
          
          partner_obj = registry.get('res.partner')
          id = partner_obj.create(cr, SUPERUSER_ID, {'name': get_customer_name(), 'city': post['city'], 'state_id': get_state_id(post['state'], int(post['country'])), 'country_id': int(post['country']), 'street': post['address1'] + ' ' + post['address2'], 'zip': int(post['zipcode'])})
          
          status = address_obj.create(cr, uid, {'address1': post['address1'], 'address2': post['address2'], 'address_type': post['address_type'], 'address_city': post['city'], 'address_country': post['country'], 'address_state': post['state'], 'address_zip': post['zipcode'], 'is_default': str(is_default), 'CIM_shipping_id': address_id, 'res_partner': str(id)})

        else:

          #setup CIM user profile if one does not exist
          CIM_profile_id = cim_profile_exists()
          
          result_ids = address_obj.search(cr, SUPERUSER_ID, [('id', '=', post['address_id']), ('create_uid', '=', uid)])
          address_result = address_obj.browse(cr, SUPERUSER_ID, result_ids)
          
          #update shipping address in CIM
          if address_result.address_type == 'shipping':
            address = authorize.Address.update(CIM_profile_id, address_result.CIM_shipping_id, {
                  'first_name': get_customer_name(),
                  'last_name': '',
                  'address': post['address1'] + ' '+ post['address2'],
                  'city': post['city'],
                  'state': post['state'],
                  'zip': post['zipcode'],
                  'country': get_country_from_id(post['country'])
            })

          status = address_obj.write(cr, uid, result_ids, {'address1': post['address1'], 'address2': post['address2'], 'address_city': post['city'], 'address_country': post['country'], 'address_state': post['state'], 'address_zip': post['zipcode']})

          partner_obj = registry.get('res.partner')
          
          partner_ids = partner_obj.search(cr, SUPERUSER_ID, [('id', '=', str(address_result.res_partner))])
          id = partner_obj.write(cr, SUPERUSER_ID, partner_ids, {'city': post['city'], 'state_id': get_state_id(post['state'], int(post['country'])), 'country_id': int(post['country']), 'street': post['address1'] + ' ' + post['address2'], 'zip': int(post['zipcode'])})

        if status:
          return json.dumps({'success': 'Successfully Saved'})
        else:
          return json.dumps({'error': 'There was an error. Please try again'})

# Set default billing, shipping address
    @http.route([
          '/shop/address/setdefault'
      ], type='http', auth='public', website=True)
    def set_default(self, **post):
        cr, uid, context, registry = request.cr, request.uid, request.context, request.registry

        if post:
          
          if post['address_id'] and post['type']:

            address_obj = registry.get('payment_authorize.checkout_address')

            #reset default fields
            result_ids = address_obj.search(cr, SUPERUSER_ID, [('address_type', '=', post['type']), ('create_uid', '=', uid)])

            for id in result_ids:
              address_obj.write(cr, SUPERUSER_ID, [id], {'is_default': '0'}, context=context)
              
            status = ''
            #set the supplied to default
            result_ids = address_obj.search(cr, SUPERUSER_ID, [('id', '=', post['address_id']), ('create_uid', '=', uid)])

            for id in result_ids:
              status = address_obj.write(cr, SUPERUSER_ID, [id], {'is_default': '1'}, context=context)

          if status:
            return "{'success': 'Successfully Saved'}"
          else:
            return "{'error': 'There was an error. Please try again'}"

# delete supplied billing or shipping address
    @http.route([
          '/shop/address/delete'
      ], type='http', auth='public', website=True)
    def delete_address(self, **post):
        cr, uid, context, registry = request.cr, request.uid, request.context, request.registry
        
        init_cim()

        if post:
          
          if post['address_id']:

            address_obj = registry.get('payment_authorize.checkout_address')

            #reset default fields
            result_ids = address_obj.search(cr, SUPERUSER_ID, [('id', '=', post['address_id']), ('create_uid', '=', uid)])
            address = address_obj.browse(cr, SUPERUSER_ID, result_ids)
  
            #delete shipping address from CIM
            if address['address_type'] == 'shipping':
              authorize.Address.delete(get_customer_cim_profile_id(), address.CIM_shipping_id)

            status = ''
            status = address_obj.unlink(cr, SUPERUSER_ID, result_ids, context=context)

          if status:
            return "{'success': 'Successfully deleted'}"
          else:
            return "{'error': 'There was an error. Please try again'}"

# Get the address details
    @http.route([
          '/shop/address/'
      ], type='http', auth='public', website=True)
    def get_address(self, **post):
        cr, uid, context, registry = request.cr, request.uid, request.context, request.registry

        if post['address_id']:
          address_obj = registry.get('payment_authorize.checkout_address')

          result_ids = address_obj.search(cr, SUPERUSER_ID, [('id', '=', post['address_id']), ('create_uid', '=', uid)])
          results = address_obj.browse(cr, SUPERUSER_ID, result_ids)

          return json.dumps({'address1': results.address1, 'address2': results.address2, 'address_city': results.address_city, 'address_country': results.address_country.id, 'address_state': results.address_state, 'address_zip': results.address_zip})

#validation of address
    def validate_form(self, data):
      
      error = {}
      fields = ['address1', 'country', 'state', 'city', 'zipcode']

      for field in fields:
        if not data.get(field):
          error[field] = 'Required Field'

      return error
      
# Setup billing and shipping address in session
    @http.route([
          '/shop/address/session'
      ], type='http', auth='public', website=True)
    def set_address_session(self, **post):

        if post['address_id'] and post['address_type']:
          request.session[post['address_type']] = post['address_id']
          return request.session['billing']+'--'+request.session['shipping']

# taken from website_sale
    def checkout_redirection(self, order):
        cr, uid, context, registry = request.cr, request.uid, request.context, request.registry

        # must have a draft sale order with lines at this point, otherwise reset
        if not order or order.state != 'draft':
            request.session['sale_order_id'] = None
            request.session['sale_transaction_id'] = None
            return request.redirect('/shop')

        # if transaction pending / done: redirect to confirmation
        tx = context.get('website_sale_transaction')
        if tx and tx.state != 'draft':
            return request.redirect('/shop/payment/confirmation/%s' % order.id)

#confirm_order override
    @http.route(['/shop/confirm_order'], type='http', auth="public", website=True)
    def confirm_order(self, **post):
        cr, uid, context, registry = request.cr, request.uid, request.context, request.registry

        order = request.website.sale_get_order(context=context)
        if not order:
            return request.redirect("/shop")

        redirection = self.checkout_redirection(order)

        #is shipping and billing selected?
        error = []
        address_obj = registry.get('payment_authorize.checkout_address')
        
        if('billing' in request.session and request.session['billing'] != '0'):
          pass
        else:  
          billing_id = address_obj.search(cr, SUPERUSER_ID, [('is_default', '=', '1'), ('address_type', '=', 'billing'), ('create_uid', '=', uid)], context=context)
          if not billing_id:
            error.append('Please select Billing address.')

        if('shipping' in request.session and request.session['shipping'] != '0'):
          pass
        else:
          shipping_id = address_obj.search(cr, SUPERUSER_ID, [('is_default', '=', '1'), ('address_type', '=', 'shipping'), ('create_uid', '=', uid)], context=context)
          if not shipping_id:
            error.append('Please select Shipping address.')

        if error:
           request.session['checkout_message'] = '<br/>'.join(error)
           redirection = request.redirect('/shop/checkout')

        if redirection:
           return redirection

  #update shipping and billing address of order
  #gather shipping info
        address_obj = registry.get('payment_authorize.checkout_address')

        shipping_id = request.session.get('shipping', '0')
        if shipping_id == '0':
          shipping_id = address_obj.search(cr, SUPERUSER_ID, [('is_default', '=', '1'), ('address_type', '=', 'shipping'), ('create_uid', '=', uid)], context=context)
        else:
          shipping_id = address_obj.search(cr, SUPERUSER_ID, [('id', '=', shipping_id), ('create_uid', '=', uid)], context=context)

        shipping_partner_id = address_obj.browse(cr, SUPERUSER_ID, shipping_id).res_partner

  #gather billing info
        billing_id = request.session.get('billing', '0')
        if billing_id == '0':
          billing_id = address_obj.search(cr, SUPERUSER_ID, [('is_default', '=', '1'), ('address_type', '=', 'billing'), ('create_uid', '=', uid)], context=context)
        else:
          billing_id = address_obj.search(cr, SUPERUSER_ID, [('id', '=', billing_id), ('create_uid', '=', uid)], context=context)

        billing_partner_id = address_obj.browse(cr, SUPERUSER_ID, billing_id).res_partner

        order_obj = registry.get('sale.order')
        ids = order_obj.search(cr, SUPERUSER_ID, [('id', '=', order.id)])
        order_obj.write(cr, SUPERUSER_ID, ids, {'partner_shipping_id': shipping_partner_id, 'partner_invoice_id': billing_partner_id})

        #update the customer info with current billing address
        customer_obj = registry.get('res.partner')
        billing_ids = customer_obj.search(cr, SUPERUSER_ID, [('id', '=', int(billing_partner_id))])
        billing_data = customer_obj.browse(cr, SUPERUSER_ID, billing_ids)
        
        user_obj = registry.get('res.users')
        user_ids = user_obj.search(cr, SUPERUSER_ID, [('id', '=', uid)])
        user_partner = user_obj.browse(cr, SUPERUSER_ID, user_ids).partner_id

        user_partner.sudo().write({'city': billing_data.city, 'state_id': int(billing_data.state_id), 'country_id': int(billing_data.country_id), 'street': billing_data.street, 'zip': billing_data.zip})

        request.session['sale_last_order_id'] = order.id

        request.website.sale_get_order(update_pricelist=True, context=context)

        return request.redirect("/shop/payment")

#overriding payment
    @http.route(auth="user")
    def payment(self, **post):
        """ Payment step. This page proposes several payment means based on available
        payment.acquirer. State at this point :

         - a draft sale order with lines; otherwise, clean context / session and
           back to the shop
         - no transaction in context / session, or only a draft one, if the customer
           did go to a payment.acquirer website but closed the tab without
           paying / canceling
        """
        cr, uid, context = request.cr, request.uid, request.context
        payment_obj = request.registry.get('payment.acquirer')
        sale_order_obj = request.registry.get('sale.order')

        order = request.website.sale_get_order(context=context)

        redirection = self.checkout_redirection(order)
        if redirection:
            return redirection

        shipping_partner_id = False
        if order:
            if order.partner_shipping_id.id:
                shipping_partner_id = order.partner_shipping_id.id
            else:
                shipping_partner_id = order.partner_invoice_id.id

        values = {
            'order': request.registry['sale.order'].browse(cr, SUPERUSER_ID, order.id, context=context)
        }
        values['errors'] = sale_order_obj._get_errors(cr, uid, order, context=context)
        values.update(sale_order_obj._get_website_data(cr, uid, order, context))

        # fetch all registered payment means
        # if tx:
        #     acquirer_ids = [tx.acquirer_id.id]
        # else:
        if not values['errors']:
            acquirer_ids = payment_obj.search(cr, SUPERUSER_ID, [('website_published', '=', True), ('company_id', '=', order.company_id.id)], context=context)
            values['acquirers'] = list(payment_obj.browse(cr, uid, acquirer_ids, context=context))
            render_ctx = dict(context, submit_class='btn btn-primary', submit_txt=_('Pay Now'))
            for acquirer in values['acquirers']:
                acquirer.button = payment_obj.render(
                    cr, SUPERUSER_ID, acquirer.id,
                    order.name,
                    order.amount_total,
                    order.pricelist_id.currency_id.id,
                    partner_id=shipping_partner_id,
                    tx_values={
                        'return_url': '/shop/payment/validate',
                    },
                    context=render_ctx)
                    
            values['checkout_address'] = request.registry.get('payment_authorize.checkout_address')
            values['request'] = request
            
        return request.website.render("website_sale.payment", values)


class AuthorizeCimCreditCardController(http.Controller):
#setup a card
    @http.route([
          '/shop/storecard'
      ], type='http', auth='user', website=True)
    def store_credit_card(self, **post):
        cr, uid, context, registry = request.cr, request.uid, request.context, request.registry
        status = ''
        
        init_cim()
        
        if post:

          errors = self.validate_form(post)
          if(errors):
            return json.dumps({'errorforhandler': errors})

          card_obj = registry.get('payment_authorize.credit_card_info')
          card_num = post['card_number'][-4:]

          if post['id']:
            result_ids = card_obj.search(cr, SUPERUSER_ID, [('id', '=', post['id']), ('create_uid', '=', uid)])

            card = card_obj.browse(cr, SUPERUSER_ID, result_ids)
            
            result = authorize.CreditCard.update(cim_profile_exists(), card.CIM_card_id, {
                'customer_type': 'individual',
                'card_number': post['card_number'],
                'expiration_month': post['month'],
                'expiration_year': post['year'],
                'card_code': post['cvv'],
            })

            status = card_obj.write(cr, uid, result_ids, {'card_num_short': card_num, 'holder_name': post['name'], 'card_type': post['card_type'], 'month': post['month'], 'year': post['year']})
          else:

            # setup first entry to be default one
            obj_count = card_obj.search_count(cr, SUPERUSER_ID, [('create_uid', '=', uid)])
            if obj_count > 0:
              is_default = 0
            else:
              is_default = 1
            
            try:

              result = authorize.CreditCard.create(cim_profile_exists(), {
                  'customer_type': 'individual',
                  'card_number': post['card_number'],
                  'expiration_month': post['month'],
                  'expiration_year': post['year'],
                  'card_code': post['cvv'],
              })

              status = card_obj.create(cr, uid, {'card_num_short': card_num, 'CIM_card_id': result.payment_id, 'holder_name': post['name'], 'user_id': uid, 'is_default': str(is_default), 'card_type': post['card_type'], 'month': post['month'], 'year': post['year']})

            except AuthorizeInvalidError as e:
              return json.dumps({'errorforhandler': eval(str(e))})

        if status:
          return self.fetch_credit_card()
        else:
          return json.dumps({'errorforhandler': 'Some error occurred'})

#fetch stored cards
    @http.route([
          '/shop/cards'
      ], type='http', auth='user', website=True)
    def fetch_credit_card(self, **post):
        cr, uid, context, registry = request.cr, request.uid, request.context, request.registry

        card_obj = registry.get('payment_authorize.credit_card_info')
        card_ids = card_obj.search(cr, SUPERUSER_ID, [('user_id', '=', uid)])
        cards = card_obj.browse(cr, SUPERUSER_ID, card_ids)
        
        if('selected_card' in request.session and request.session['selected_card']):
          selected_card = request.session['selected_card']
        else:
          selected_card = 0

        return request.website.render("payment_authorize_cim.cards_list", {'cards': cards, 'selected_card': selected_card})

#delete a card
    @http.route([
          '/shop/card/delete'
      ], type='http', auth='user', website=True)
    def delete_credit_card(self, **post):
        cr, uid, context, registry = request.cr, request.uid, request.context, request.registry
        
        init_cim()

        if post:

          card_obj = registry.get('payment_authorize.credit_card_info')
          card_ids = card_obj.search(cr, SUPERUSER_ID, [('user_id', '=', uid), ('id', '=', post['id'])])
          card = card_obj.browse(cr, SUPERUSER_ID, card_ids)

          result = authorize.CreditCard.delete(cim_profile_exists(), card.CIM_card_id)
          card_obj.unlink(cr, SUPERUSER_ID, card_ids)

          #return request.website.render("payment_authorize_cim.cards_list", {'cards': cards})
          return self.fetch_credit_card()

#set selected card in session
    @http.route([
          '/shop/card/selected'
      ], type='http', auth='user', website=True)
    def select_credit_card(self, **post):
        cr, uid, context, registry = request.cr, request.uid, request.context, request.registry

        if post:

          request.session['selected_card'] = post['id']
          
        return self.fetch_credit_card()

#make a card default
    @http.route([
          '/shop/card/default'
      ], type='http', auth='user', website=True)
    def default_credit_card(self, **post):
        cr, uid, context, registry = request.cr, request.uid, request.context, request.registry

        if post:
          status = ''
          card_obj = registry.get('payment_authorize.credit_card_info')

          if post['id']:
            result_ids = card_obj.search(cr, SUPERUSER_ID, [('user_id', '=', uid)])
            status = card_obj.write(cr, SUPERUSER_ID, result_ids, {'is_default': '0'})

            result_ids = card_obj.search(cr, SUPERUSER_ID, [('id', '=', post['id']), ('create_uid', '=', uid)])
            status = card_obj.write(cr, SUPERUSER_ID, result_ids, {'is_default': '1'})

        if status:
          return self.fetch_credit_card()
        else:
          return json.dumps({'error': 'Some error occurred'})

#get card details
    @http.route([
          '/shop/card/detail'
      ], type='http', auth='user', website=True)
    def credit_detail(self, **post):
        cr, uid, context, registry = request.cr, request.uid, request.context, request.registry
        
        if post['id']:
          card_obj = registry.get('payment_authorize.credit_card_info')
          card_ids = card_obj.search(cr, SUPERUSER_ID, [('user_id', '=', uid), ('id', '=', post['id'])])
          card = card_obj.browse(cr, SUPERUSER_ID, card_ids)

          return json.dumps({'card_type': card.card_type, 'card_num_short': card.card_num_short, 'holder_name': card.holder_name})

#validation of cards
    def validate_form(self, data):
      
      error = {}
      fields = ['card_type', 'name', 'card_number', 'month', 'year', 'cvv']

      for field in fields:
        if not data.get(field):
          error[field] = 'Required Field'

      return error

#non class methods
def cim_profile_exists():
  cr, uid, context, registry = request.cr, request.uid, request.context, request.registry

  user_obj = registry.get('res.users')
  user_ids = user_obj.search(cr, SUPERUSER_ID, [('id', '=', uid)])
  user = user_obj.browse(cr, SUPERUSER_ID, user_ids)

  if user.CIM_profile_id:
    return user.CIM_profile_id
  else:
    return False

def setup_cim_profile():
  cr, uid, context, registry = request.cr, request.uid, request.context, request.registry

  user_obj = registry.get('res.users')
  user_ids = user_obj.search(cr, SUPERUSER_ID, [('id', '=', uid)])

  result = authorize.Customer.create()
  user_obj.write(cr, SUPERUSER_ID, user_ids, {'CIM_profile_id': result.customer_id})

  return result.customer_id

def get_customer_name():
  cr, uid, context, registry = request.cr, request.uid, request.context, request.registry

  user_obj = registry.get('res.users')
  user_ids = user_obj.search(cr, SUPERUSER_ID, [('id', '=', uid)])
  user = user_obj.browse(cr, SUPERUSER_ID, user_ids)

  return user.partner_id.display_name

def get_customer_cim_profile_id():
  cr, uid, context, registry = request.cr, request.uid, request.context, request.registry

  user_obj = registry.get('res.users')
  user_ids = user_obj.search(cr, SUPERUSER_ID, [('id', '=', uid)])
  user = user_obj.browse(cr, SUPERUSER_ID, user_ids)

  return user.CIM_profile_id

def get_country_from_id(id):
  cr, uid, context, registry = request.cr, request.uid, request.context, request.registry

  country_obj = registry.get('res.country')
  country_ids = country_obj.search(cr, SUPERUSER_ID, [('id', '=', id)])
  country = country_obj.browse(cr, SUPERUSER_ID, country_ids)

  return country.name

def get_state_id(state, country_id):
  cr, uid, context, registry = request.cr, request.uid, request.context, request.registry
  
  state_obj = registry.get('res.country.state')
  result = state_obj.search_count(cr, SUPERUSER_ID, [('name', '=', state)])
  
  if(result == 0):
    state = state_obj.create(cr, SUPERUSER_ID, {'name': state, 'country_id': country_id, 'code': 'na'})
    state_id = state
  else:
    state_ids = state_obj.search(cr, SUPERUSER_ID, [('name', '=', state)])
    state = state_obj.browse(cr, SUPERUSER_ID, state_ids)
    state_id = state.id

  return state_id



  