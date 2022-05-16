from io import StringIO
import pytest

from invoices.base.pages import invoices


class TestClass:

  def test_create_product_list_positive(self):
    """This test method tests the function that is used to send stock-change requests to uweb3 warehouse."""
    test_products = [
        {
            'name': 'some_name',
            'quantity': 5
        },
        {
            'name': 'some_name',
            'quantity': 10
        },
    ]
    results = invoices.CreateCleanProductList(test_products)
    assert [{'name': 'some_name', 'quantity': 15}] == results

  def test_create_product_list_negative(self):
    test_products = [
        {
            'name': 'some_name',
            'quantity': 5
        },
        {
            'name': 'some_name',
            'quantity': 10
        },
    ]
    results = invoices.CreateCleanProductList(test_products, negative_abs=True)
    assert [{'name': 'some_name', 'quantity': -15}] == results

  def test_create_product_list_multiple_items(self):
    test_products = [{
        'name': 'some_name',
        'quantity': 5
    }, {
        'name': 'some_name',
        'quantity': 10
    }, {
        'name': 'another_product',
        'quantity': 1
    }, {
        'name': 'another_product',
        'quantity': 100
    }, {
        'name': 'yet another product',
        'quantity': 1000000
    }]
    results = invoices.CreateCleanProductList(test_products)
    assert [
        {
            'name': 'some_name',
            'quantity': 15
        },
        {
            'name': 'another_product',
            'quantity': 101
        },
        {
            'name': 'yet another product',
            'quantity': 1000000
        },
    ] == results

  def test_mt940_regex_search(self):
    data = None
    with open('tests/test_mt940.sta', 'r') as f:
      data = f.read()
    io_file = StringIO(data)
    results = invoices.regex_search(io_file, invoices.INVOICE_REGEX_PATTERN)
    assert [
        {
            'invoice':
                'PF-2022-001',  # First pro forma invoice that was referenced in .sta
            'amount': '100.76'
        },
        {
            'invoice': '2022-001',  # Fist actual invoice that was referenced
            'amount': '65.20'
        },
        {
            'invoice': '2022-002',  # Second invoice
            'amount': '952.10'
        }
    ] == results
