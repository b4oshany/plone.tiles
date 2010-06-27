import unittest2 as unittest
import doctest
from plone.testing import Layer, layered
from plone.testing import zca, z2

from zope.configuration import xmlconfig

# For directive tests

from zope.interface import Interface
from zope import schema

from plone.tiles import Tile, PersistentTile

class IDummySchema(Interface):
    foo = schema.TextLine(title=u"Foo")

class IDummyContext(Interface):
    pass

class IDummyLayer(Interface):
    pass

class DummyTile(Tile):
    def __call__(self):
        return u"dummy"

class DummyTileWithTemplate(PersistentTile):
    pass

class PloneTiles(Layer):
    defaultBases = (z2.INTEGRATION_TESTING,)

    def setUp(self):
        import plone.tiles
        self['configurationContext'] = context = zca.stackConfigurationContext(self.get('configurationContext'))
        xmlconfig.file('configure.zcml', plone.tiles, context=context)

PLONE_TILES = PloneTiles()

def test_suite():
    return unittest.TestSuite((        
        layered(doctest.DocFileSuite('tiles.txt', 'directives.txt',
                                     'data.txt', 'esi.txt'),
                layer=PLONE_TILES),
        ))
