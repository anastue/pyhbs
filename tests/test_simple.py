from unittest import TestCase

class TestSimple(TestCase):
    def test_import(self):
        import pyhbs
        pyhbs.render_source
        pyhbs.render_file
        pyhbs.register_helper

def test_success():
    assert True
