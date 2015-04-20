import xml.etree.ElementTree as E

from configuration import Configuration
from address import Address
from bank_account import BankAccount
from batch import Batch
from credit_card import CreditCard
from customer import Customer
from environment import Environment
from exceptions import AuthorizeError
from exceptions import AuthorizeConnectionError
from exceptions import AuthorizeResponseError
from exceptions import AuthorizeInvalidError
from recurring import Recurring
from transaction import Transaction
import apis


# Monkeypatch the ElementTree module so that we can use CDATA element types
E._original_serialize_xml = E._serialize_xml
def _serialize_xml(write, elem, *args, **kwargs):
    if elem.tag == '![CDATA[':
        write('<![CDATA[%s]]>' % elem.text)
        return
    return E._original_serialize_xml(write, elem, *args, **kwargs)
E._serialize_xml = E._serialize['xml'] = _serialize_xml
