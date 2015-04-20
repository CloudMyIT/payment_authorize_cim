# -*- coding: utf-'8' "-*-"

import hashlib
import hmac
import logging
import time
import urlparse

from openerp import api, fields, models
from openerp.addons.payment.models.payment_acquirer import ValidationError
from openerp.addons.payment_authorize_cim.controllers.main import AuthorizeCimController
from openerp.tools.float_utils import float_compare

_logger = logging.getLogger(__name__)


class PaymentAcquirerAuthorizeCim(models.Model):
    _inherit = 'payment.acquirer'
    
    @api.model
    def _get_providers(self):
        providers = super(PaymentAcquirerAuthorizeCim, self)._get_providers()
        providers.append(['authorize_cim', 'Authorize.Net CIM'])
        return providers

    authorize_login = fields.Char(string='Account Id', required_if_provider='authorize_cim')
    authorize_transaction_key = fields.Char(string='Secret Key', required_if_provider='authorize_cim')

    def _authorize_generate_hashing(self, values):
        data = '^'.join([
            values['x_login'],
            values['x_fp_sequence'],
            values['x_fp_timestamp'],
            values['x_amount'],
            values['x_currency_code']])
        return hmac.new(str(values['x_trans_key']), data, hashlib.md5).hexdigest()

    @api.multi
    def authorize_cim_form_generate_values(self, partner_values, tx_values):
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].get_param('web.base.url')
        authorize_tx_values = dict(tx_values)
        temp_authorize_tx_values = {
            'x_amount': str(tx_values['amount']),
            'x_currency_code': tx_values['currency'] and tx_values['currency'].name or '',
            'address': partner_values['address'],
            'city': partner_values['city'],
            'country': partner_values['country'] and partner_values['country'].name or '',
            'email': partner_values['email'],
            'zip': partner_values['zip'],
            'first_name': partner_values['first_name'],
            'last_name': partner_values['last_name'],
            'phone': partner_values['phone'],
            'state': partner_values.get('state') and partner_values['state'].name or '',
        }
        authorize_tx_values.update(temp_authorize_tx_values)
        return partner_values, authorize_tx_values

    @api.multi
    def authorize_cim_get_form_action_url(self):
        self.ensure_one()
        return '/payment/process'

class TxAuthorizeCim(models.Model):
    _inherit = 'payment.transaction'

    authorize_txnid = fields.Char(string='Transaction ID')

#Billing and Shipping address
class authorize_checkout_address(models.Model):
  _name = 'payment_authorize.checkout_address'

  address1 = fields.Char(string="Address 1", required=True)
  address2 = fields.Char(string="Address 2", required=False)
  address_type = fields.Char(string="Address Type", required=True)
  address_city = fields.Char(string="Address City", required=True)
  address_state = fields.Char(string="Address State", required=True)
  #address_country = fields.Char(string="Address Country", required=True)
  address_zip = fields.Char(string="Address Zip", required=True)
  is_default = fields.Char(string="Is Default", required=False)
  CIM_shipping_id = fields.Char(string="CIM shipping id", required=False)
  res_partner = fields.Char(string="Partner id", required=False)

  address_country = fields.Many2one('res.country', ondelete='set null', string="Country Name", index=True)

  def check_address(self, type, request):
    cr, uid, context, registry = request.cr, request.uid, request.context, request.registry

    if(type in request.session and request.session[type] != '0'):
      result_ids = self.search(cr, uid, [('id', '=', request.session[type])])
      result = self.browse(cr, uid, result_ids)
    else:
      result_ids = self.search(cr, uid, [('address_type', '=', type), ('is_default', '=', '1')])
      result = self.browse(cr, uid, result_ids)

    return result[0]

#Credit card minimal info and CIM tokens
class authorize_credit_card_info(models.Model):
  _name = 'payment_authorize.credit_card_info'
  
  card_num_short = fields.Char(string="Last 4 digits of Card", required=True)
  holder_name = fields.Char(string="Holder's Name", required=True)
  is_default = fields.Char(string="Is Default", required=False)
  user_id = fields.Many2one('res.users', ondelete='set null', string="User Id", index=True)
  CIM_card_id = fields.Char(string="CIM card id", required=True)
  card_type = fields.Char(string="CIM card type", required=True)
  month = fields.Char(string="month", required=True)
  year = fields.Char(string="year", required=True)

#Override res.users
class authorize_users(models.Model):
  _inherit = "res.users"

  CIM_profile_id = fields.Char(string="CIM profile id", required=False)