from payment_profile_api import PaymentProfileAPI
from openerp.addons.payment_authorize_cim.lib.authorize.schemas import CreateCreditCardSchema
from openerp.addons.payment_authorize_cim.lib.authorize.schemas import UpdateCreditCardSchema
from openerp.addons.payment_authorize_cim.lib.authorize.schemas import ValidateCreditCardSchema
from openerp.addons.payment_authorize_cim.lib.authorize.xml_data import *


class CreditCardAPI(PaymentProfileAPI):

    def create(self, customer_id, params={}):
        card = self._deserialize(CreateCreditCardSchema(), params)
        return self.api._make_call(self._create_request(customer_id, card))

    def update(self, customer_id, payment_id, params={}):
        card = self._deserialize(UpdateCreditCardSchema(), params)
        return self.api._make_call(self._update_request(customer_id, payment_id, card))

    def validate(self, customer_id, payment_id, params={}):
        card = self._deserialize(ValidateCreditCardSchema(), params)
        return self.api._make_call(self._validate_request(customer_id, payment_id, card))

    # The following methods generate the XML for the corresponding API calls.
    # This makes unit testing each of the calls easier.
    def _create_request(self, customer_id, card={}):
        return self._make_xml('createCustomerPaymentProfileRequest', customer_id, None, params=card)

    def _update_request(self, customer_id, payment_id, card={}):

        # Issue 30: If only the last 4 digits of a credit card are provided,
        # add the additional XXXX character mask that is required.
        if len(card['card_number']) == 4:
          card['card_number'] = 'XXXX' + card['card_number']

        return self._make_xml('updateCustomerPaymentProfileRequest', customer_id, payment_id, params=card)

    def _validate_request(self, customer_id, payment_id, card={}):
        request = self.api._base_request('validateCustomerPaymentProfileRequest')
        E.SubElement(request, 'customerProfileId').text = customer_id
        E.SubElement(request, 'customerPaymentProfileId').text = payment_id

        if 'address_id' in card:
            E.SubElement(request, 'customerShippingAddressId').text = card['address_id']

        if 'card_code' in card:
            E.SubElement(request, 'cardCode').text = str(card['card_code'])

        E.SubElement(request, 'validationMode').text = card['validation_mode']

        return request
