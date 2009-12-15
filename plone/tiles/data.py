import logging
import urllib

from zope.interface import implements
from zope.component import adapts, queryUtility

from zope.schema import getFieldsInOrder, getFields
from zope.schema.interfaces import ISequence

from zope import schema

from zope.annotation.interfaces import IAnnotations

from plone.tiles.interfaces import ITileType
from plone.tiles.interfaces import ITile
from plone.tiles.interfaces import IPersistentTile
from plone.tiles.interfaces import ITileDataManager

from persistent.dict import PersistentDict

ANNOTATIONS_KEY_PREFIX = u'plone.tiles.data'
LOGGER = logging.getLogger('plone.tiles')

class TransientTileDataManager(object):
    """A data manager for transient tile data, which reads data from the
    request query string.
    """
    
    implements(ITileDataManager)
    adapts(ITile)
    
    def __init__(self, tile):
        self.tile = tile
        self.tileType = queryUtility(ITileType, name=tile.__type_name__)
    
    def get(self):
        # If we don't have a schema, just take the request
        if self.tileType is None or self.tileType.schema is None:
            return self.tile.request.form.copy()
    
        # Try to decode the form data properly if we can
        try:
            return decode(self.tile.request.form, self.tileType.schema, missing=True)
        except (ValueError, UnicodeDecodeError,):
            LOGGER.exception(u"Could not convert form data to schema")
            return self.tile.request.form.copy()
    
    def set(self, data):
        self.tile.request.form.clear()
        self.tile.request.form.update(data)
    
    def delete(self):
        self.tile.request.form.clear()

class PersistentTileDataManager(object):
    """A data reader for persistent tiles operating on annotatable contexts.
    The data is retrieved from an annotation.
    """
    
    implements(ITileDataManager)
    adapts(IPersistentTile)
    
    def __init__(self, tile):
        self.tile = tile
        self.tileType = queryUtility(ITileType, name=tile.__type_name__)
        self.annotations = IAnnotations(self.tile.context)
        self.key = "%s.%s" % (ANNOTATIONS_KEY_PREFIX, tile.__name__,)
        
    def get(self):
        data = dict(self.annotations.get(self.key, {}))
        if self.tileType is not None and self.tileType.schema is not None:
            for name, field in getFields(self.tileType.schema).items():
                if name not in data:
                    data[name] = field.missing_value
        return data

    def set(self, data):
        self.annotations[self.key] = PersistentDict(data)
    
    def delete(self):
        if self.key in self.annotations:
            del self.annotations[self.key]

# Encoding

# Types not in this dict or explicitly set to None are not supported and will
# result in a ValueError.

type_to_converter = {
    
    # Strings - not type converted

    schema.BytesLine        : '',
    schema.ASCIILine        : '',
    schema.TextLine         : '',
    
    schema.URI              : '',
    schema.Id               : '',
    schema.DottedName       : '',
    
    # Choice - assumes the value of the vocabulary is a string!
    
    schema.Choice           : '',
    
    # Text types - may allow newlines
    
    schema.Bytes            : 'text',
    schema.Text             : 'text',
    schema.ASCII            : 'text',

    # Numeric types

    schema.Int              : 'long',
    schema.Float            : 'float',

    # Bools - note that False is encoded as ''
    
    schema.Bool             : 'boolean',

    # Sequence types
    
    schema.Tuple            : 'tuple',
    schema.List             : 'list',
    
}

def encode(data, schema, ignore=()):
    """Given a data dictionary with key/value pairs and schema, return an
    encoded query string. This is similar to urllib.urlencode(), but field
    names will include the appropriate field type converters, e.g. an int
    field will be encoded as fieldname:int=123. Fields not found in the data
    dict will be ignored, and items in the dict not in the schema will also
    be ignored. Additional fields to ignore can be passed with the 'ignore'
    parameter. If any fields cannot be converted, a KeyError will be raised.
    """
    
    encode = []
    
    for name, field in getFieldsInOrder(schema):
        if name in ignore or name not in data:
            continue
        
        converter = type_to_converter.get(field.__class__, None)
        if converter is None:
            raise KeyError(u"Cannot URL encode %s of type %s" % (name, field.__class__,))
        
        encoded_name = name
        if converter:
            encoded_name = "%s:%s" % (name, converter,)
        
        value = data[name]
        if value is None:
            continue
        
        if ISequence.providedBy(field):
            value_type_converter = type_to_converter.get(field.value_type.__class__, None)
            if value_type_converter is None:
                raise KeyError(u"Cannot URL encode value type for %s of type %s : %s" % \
                                (name, field.__class__, field.value_type.__class__,))
            
            if value_type_converter:
                encoded_name = "%s:%s:%s" % (name, value_type_converter, converter,)
            
            for item in value:
                
                if isinstance(item, bool):
                    item = item and '1' or ''
                
                encode.append((encoded_name, item,))
                
        else:
            
        
            # The :bool converter just does bool() value, but urlencode() does
            # str() on the object. The result is False => 'False' => True :(
            if isinstance(value, bool):
                value = value and '1' or ''
        
            encode.append((encoded_name, value))
    
    return urllib.urlencode(encode)

# Decoding

def decode(data, schema, missing=True):
    """Decode a data dict according to a schema. The returned dictionary will
    contain only keys matching schema names, and will force type values 
    appropriately.
    
    This function is only necessary because the encoders used by encode()
    are not sufficiently detailed to always return the exact type expected
    by a field, e.g. resulting in ascii/unicode discrepancies.
    
    If missing is True, fields that are in the schema but not the field will
    be set to field.missing_value. Otherwise, they are ignored.
    """
    
    decoded = {}
    
    for name, field in getFields(schema).items():
        if name not in data:
            if missing:
                decoded[name] = field.missing_value
            continue
        
        value = data[name]
        
        field_type = field._type
        if isinstance(field_type, (tuple, list,)):
            field_type = field_type[-1]
        
        if ISequence.providedBy(field):
            converted = []
            
            value_type_field_type = field.value_type._type
            if isinstance(value_type_field_type, (tuple, list,)):
                value_type_field_type = value_type_field_type[-1]
            
            for item in value:
                if not isinstance(item, field.value_type._type):
                    item = value_type_field_type(item)
                converted.append(item)
            
            value = converted
        
        if not isinstance(value, field._type):
            value = field_type(value)

        decoded[name] = value

    return decoded