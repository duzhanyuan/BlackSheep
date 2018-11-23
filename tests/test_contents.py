import pytest
from typing import List
from blacksheep import HttpContent
from blacksheep.contents import (parse_www_form,
                                 write_www_form_urlencoded,
                                 parse_multipart_form_data,
                                 parse_content_disposition_header,
                                 extract_multipart_form_data_boundary,
                                 FormPart,
                                 MultiPartFormData)
from blacksheep.scribe import write_chunks


def bytes_equals_ignoring_crlf(with_crlf, with_lf):
    return [i for i in with_crlf if i != 13] == [i for i in with_lf]


@pytest.mark.asyncio
async def test_chunked_encoding_with_generated_content():

    def data_generator():
        yield b'{"hello":"world",'
        yield b'"lorem":'
        yield b'"ipsum","dolor":"sit"'
        yield b',"amet":"consectetur"}'

    content = HttpContent(b'application/json', data_generator)

    gen = data_generator()

    async for chunk in write_chunks(content):
        try:
            generator_bytes = next(gen)
        except StopIteration:
            assert chunk == b'0\r\n\r\n'
        else:
            assert chunk == hex(len(generator_bytes))[2:].encode() \
                   + b'\r\n' + generator_bytes + b'\r\n'


@pytest.mark.parametrize('content,expected_result', [
    [
        b'Name=Gareth+Wylie&Age=24&Formula=a+%2B+b+%3D%3D+13%25%21',
        {
            b'Name': [b'Gareth Wylie'],
            b'Age': [b'24'],
            b'Formula': [b'a + b == 13%!']
        }
    ],
    [
        b'a=12&b=24&a=33',
        {
            b'a': [b'12', b'33'],
            b'b': [b'24']
        }
    ],
])
def test_form_urlencoded_parser(content, expected_result):
    data = parse_www_form(content)
    assert expected_result == data


@pytest.mark.parametrize('data,expected_result', [
    [
        {
            'Name': 'Gareth Wylie',
            'Age': 24,
            'Formula': 'a + b == 13%!'
        }, b'Name=Gareth+Wylie&Age=24&Formula=a+%2B+b+%3D%3D+13%25%21'
    ],
    [
        [('a', '13'), ('a', '24'), ('b', '5'), ('a', '66')],
        b'a=13&a=24&b=5&a=66'
    ],
    [
        {
            'a': [13, 24, 66],
            'b': [5]
        },
        b'a=13&a=24&a=66&b=5'
    ]
])
def test_form_urlencoded_writer(data, expected_result):
    content = write_www_form_urlencoded(data)
    assert expected_result == content


@pytest.mark.asyncio
async def test_multipart_form_data():
    data = MultiPartFormData([
        FormPart(b'text1', b'text default'),
        FormPart(b'text2', 'aωb'.encode('utf8')),
        FormPart(b'file1', b'Content of a.txt.\n', b'text/plain', b'a.txt'),
        FormPart(b'file2', b'<!DOCTYPE html><title>Content of a.html.</title>\n', b'text/html', b'a.html'),
        FormPart(b'file3', 'aωb'.encode('utf8'), b'application/octet-stream', b'binary'),
    ])

    whole = b''
    async for chunk in data.get_parts():
        whole += chunk

    expected_result_lines = [
        data.boundary,
        b'Content-Disposition: form-data; name="text1"',
        b'',
        b'text default',
        data.boundary,
        b'Content-Disposition: form-data; name="text2"',
        b'',
        'aωb'.encode('utf8'),
        data.boundary,
        b'Content-Disposition: form-data; name="file1"; filename="a.txt"',
        b'Content-Type: text/plain',
        b'',
        b'Content of a.txt.',
        b'',
        data.boundary,
        b'Content-Disposition: form-data; name="file2"; filename="a.html"',
        b'Content-Type: text/html',
        b'',
        b'<!DOCTYPE html><title>Content of a.html.</title>',
        b'',
        data.boundary,
        b'Content-Disposition: form-data; name="file3"; filename="binary"',
        b'Content-Type: application/octet-stream',
        b'',
        'aωb'.encode('utf8'),
        data.boundary + b'--'
    ]

    assert bytes_equals_ignoring_crlf(whole, b'\n'.join(expected_result_lines))


def test_parse_multipart_form_data():
    boundary = b'---------------------0000000000000000000000001'

    content = b'\n'.join([
        boundary,
        b'Content-Disposition: form-data; name="text1"',
        b'',
        b'text default',
        boundary,
        b'Content-Disposition: form-data; name="text2"',
        b'',
        'aωb'.encode('utf8'),
        boundary,
        b'Content-Disposition: form-data; name="file1"; filename="a.txt"',
        b'Content-Type: text/plain',
        b'',
        b'Content of a.txt.',
        b'',
        boundary,
        b'Content-Disposition: form-data; name="file2"; filename="a.html"',
        b'Content-Type: text/html',
        b'',
        b'<!DOCTYPE html><title>Content of a.html.</title>',
        b'',
        boundary,
        b'Content-Disposition: form-data; name="file3"; filename="binary"',
        b'Content-Type: application/octet-stream',
        b'',
        'aωb'.encode('utf8'),
        boundary + b'--'
    ])

    data = list(parse_multipart_form_data(content, boundary))  # type: List[FormPart]

    assert data is not None
    assert len(data) == 5

    assert data[0].name == b'text1'
    assert data[0].file_name is None
    assert data[0].content_type is None
    assert data[0].data == b'text default'

    assert data[1].name == b'text2'
    assert data[1].file_name is None
    assert data[1].content_type is None
    assert data[1].data == 'aωb'.encode('utf8')

    assert data[2].name == b'file1'
    assert data[2].file_name == b'a.txt'
    assert data[2].content_type == b'text/plain'
    assert data[2].data == b'Content of a.txt.\n'

    assert data[3].name == b'file2'
    assert data[3].file_name == b'a.html'
    assert data[3].content_type == b'text/html'
    assert data[3].data == b'<!DOCTYPE html><title>Content of a.html.</title>\n'

    assert data[4].name == b'file3'
    assert data[4].file_name == b'binary'
    assert data[4].content_type == b'application/octet-stream'
    assert data[4].data == 'aωb'.encode('utf8')


@pytest.mark.parametrize('value, expected_result', [
    [
        b'Content-Disposition: form-data; name="file2"; filename="a.html"',
        (b'form-data', b'file2', b'a.html')
    ],
    [
        b'Content-Disposition: form-data; name="example"',
        (b'form-data', b'example', None)
    ],
    [
        b'Content-Disposition: form-data; name="hello-world"',
        (b'form-data', b'hello-world', None)
    ],
    [
        b'Content-Disposition: form-data; name="hello-world";',
        (b'form-data', b'hello-world', None)
    ]
])
def test_parsing_content_disposition_header(value, expected_result):
    parsed = parse_content_disposition_header(value)
    assert parsed == expected_result


@pytest.mark.parametrize('value,expected_result', [
    (b'multipart/form-data; boundary=---------------------1321321',
     b'---------------------1321321'),
    (b'multipart/form-data; boundary=--4ed15c90-6b4b-457f-99d8-e965c76679dd',
     b'--4ed15c90-6b4b-457f-99d8-e965c76679dd'),
    (b'multipart/form-data; boundary=--4ed15c90-6b4b-457f-99d8-e965c76679dd',
     b'--4ed15c90-6b4b-457f-99d8-e965c76679dd'),
    (b'multipart/form-data; boundary=-------------AAAA12345',
     b'-------------AAAA12345'),
])
def test_extract_multipart_form_data_boundary(value, expected_result):
    boundary = extract_multipart_form_data_boundary(value)
    assert boundary == expected_result