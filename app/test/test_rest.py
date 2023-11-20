#!/usr/bin/env python3

import unittest
import aiohttp
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from ..rest import put_metadata_format
import time
import struct
from random import randbytes
import base64

URL_BASE = 'http://localhost:8000/'

class TestRest(unittest.IsolatedAsyncioTestCase):

    def editor_public_private_keys(self):
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key().public_bytes_raw()
        return public_key, private_key

    def generate_info_hash_and_pok(self, editor_public_key):
        uri_private_key = Ed25519PrivateKey.generate()
        info_hash = uri_private_key.public_key().public_bytes_raw()
        pok = uri_private_key.sign(editor_public_key)
        return info_hash, pok
    
    async def put(
        self,
        editor_public_key,
        editor_private_key,
        version,
        info_hash,
        pok,
        counter,
        expiration,
        payload
    ):
        container = struct.pack(put_metadata_format,
            version,
            info_hash,
            pok,
            counter,
            expiration
        ) + payload

        container_signed = container + editor_private_key.sign(container)

        editor_public_key_base64 = base64.urlsafe_b64encode(editor_public_key).decode()

        url = f'{URL_BASE}{editor_public_key_base64}'

        async with aiohttp.ClientSession() as session:

            # Put the data
            async with session.put(
                url,
                data=container_signed) as response:

                return url, container_signed, response.status, await response.read()

    async def test_good_put(self):
        # All the arguments to the input
        editor_public_key, editor_private_key = self.editor_public_private_keys()
        info_hash, pok = self.generate_info_hash_and_pok(editor_public_key)

        url, container_signed, status, response = await self.put(
            editor_public_key=editor_public_key,
            editor_private_key=editor_private_key,
            info_hash=info_hash,
            pok=pok,
            version=0,
            counter=123,
            expiration=int(time.time() + 100),
            payload=randbytes(100)
        )

        self.assertEqual(status, 200)
        self.assertEqual(response, b'')

        # Make sure you can get the data
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                resp = await response.read()
                self.assertEqual(resp, container_signed)

    async def test_replace_inc_counter(self):
        # fix the expiration
        expiration = int(time.time()) + 100

        # Put some data
        editor_public_key, editor_private_key = self.editor_public_private_keys()
        info_hash, pok = self.generate_info_hash_and_pok(editor_public_key)
        url, container_signed, status, response = await self.put(
            editor_public_key=editor_public_key,
            editor_private_key=editor_private_key,
            info_hash=info_hash,
            pok=pok,
            version=0,
            counter=123,
            expiration=expiration,
            payload=randbytes(100)
        )
        self.assertEqual(status, 200)
        self.assertEqual(response, b'')

        # Replace it with increasingly larger counters
        for counter in [124, 125, 1000, 9999]:
            url2, container_signed2, status, response = await self.put(
                editor_public_key=editor_public_key,
                editor_private_key=editor_private_key,
                info_hash=info_hash,
                pok=pok,
                version=0,
                counter=counter,
                expiration=expiration,
                payload=randbytes(100)
            )
            self.assertEqual(status, 200)
            # It should return the previous value
            self.assertEqual(response, container_signed)
            self.assertEqual(url, url2)

            # Getting should return the latest value
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    resp = await response.read()
                    self.assertEqual(resp, container_signed2)
            container_signed = container_signed2

    async def test_replace_inc_counter_inc_expiration(self):
        init_counter = 123
        init_expiration = int(time.time())

        # Put some data
        editor_public_key, editor_private_key = self.editor_public_private_keys()
        info_hash, pok = self.generate_info_hash_and_pok(editor_public_key)
        url, container_signed, status, response = await self.put(
            editor_public_key=editor_public_key,
            editor_private_key=editor_private_key,
            info_hash=info_hash,
            pok=pok,
            version=0,
            counter=init_counter,
            expiration=init_expiration,
            payload=randbytes(100)
        )
        self.assertEqual(status, 200)
        self.assertEqual(response, b'')

        # Replace it with increasingly larger counters
        for offset_c, offset_e in [[1, 1], [2, 1], [100, 100], [9999, 100]]:
            url2, container_signed2, status, response = await self.put(
                editor_public_key=editor_public_key,
                editor_private_key=editor_private_key,
                info_hash=info_hash,
                pok=pok,
                version=0,
                counter=init_counter+offset_c,
                expiration=init_expiration+offset_e,
                payload=randbytes(100)
            )
            self.assertEqual(status, 200)
            # It should return the previous value
            self.assertEqual(response, container_signed)
            self.assertEqual(url, url2)

            # Getting should return the latest value
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    resp = await response.read()
                    self.assertEqual(resp, container_signed2)
            container_signed = container_signed2

    async def test_replace_dec_counter(self):
        # Put some data
        editor_public_key, editor_private_key = self.editor_public_private_keys()
        info_hash, pok = self.generate_info_hash_and_pok(editor_public_key)
        url, container_signed, status, response = await self.put(
            editor_public_key=editor_public_key,
            editor_private_key=editor_private_key,
            info_hash=info_hash,
            pok=pok,
            version=0,
            counter=42069,
            expiration=int(time.time() + 100),
            payload=randbytes(0)
        )
        self.assertEqual(status, 200)
        self.assertEqual(response, b'')

        # Try to replace it but with a smaller counter
        for counter in [0, 500, 42069, 42069]:
            url2, container_signed2, status, response = await self.put(
                editor_public_key=editor_public_key,
                editor_private_key=editor_private_key,
                info_hash=info_hash,
                pok=pok,
                version=0,
                counter=counter,
                expiration=int(time.time() + 100),
                payload=randbytes(100)
            )
            self.assertEqual(status, 200)
            # It should return the previous value
            self.assertEqual(response, container_signed)
            self.assertEqual(url, url2)

            # Getting should return the ORIGINAL value
            # because the counters are <= the existing counter
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    resp = await response.read()
                    self.assertEqual(resp, container_signed)

    async def test_replace_dec_expiration(self):
        expiration = int(time.time()) + 100

        # Put some data
        editor_public_key, editor_private_key = self.editor_public_private_keys()
        info_hash, pok = self.generate_info_hash_and_pok(editor_public_key)
        url, container_signed, status, response = await self.put(
            editor_public_key=editor_public_key,
            editor_private_key=editor_private_key,
            info_hash=info_hash,
            pok=pok,
            version=0,
            counter=42069,
            expiration=expiration,
            payload=randbytes(0)
        )
        self.assertEqual(status, 200)
        self.assertEqual(response, b'')

        # Increase the counter, but decrease expiration
        for offset in [1, 100, int(time.time())-10]:
            url2, container_signed2, status, response = await self.put(
                editor_public_key=editor_public_key,
                editor_private_key=editor_private_key,
                info_hash=info_hash,
                pok=pok,
                version=0,
                counter=42070,
                expiration=expiration - offset,
                payload=randbytes(100)
            )
            self.assertEqual(status, 200)
            # It should return the previous value
            self.assertEqual(response, container_signed)
            self.assertEqual(url, url2)

            # Getting should return the ORIGINAL value
            # because the expiration is < the existing expiration
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    resp = await response.read()
                    self.assertEqual(resp, container_signed)

    async def test_invalid_pok(self):
        editor_public_key, editor_private_key = self.editor_public_private_keys()
        info_hash, pok = self.generate_info_hash_and_pok(editor_public_key)
        info_hash2, pok2 = self.generate_info_hash_and_pok(editor_public_key)
        url, container_signed, status, response = await self.put(
            editor_public_key=editor_public_key,
            editor_private_key=editor_private_key,
            info_hash=info_hash,
            # Wrong POK for this info hash
            pok=pok2,
            version=0,
            counter=1,
            expiration=int(2*time.time()),
            payload=randbytes(0)
        )

        self.assertEqual(status, 401)
        self.assertEqual(response, b'invalid proof of knowledge')

    async def test_invalid_signature(self):
        editor_public_key, editor_private_key = self.editor_public_private_keys()
        editor_public_key2, editor_private_key2 = self.editor_public_private_keys()
        info_hash, pok = self.generate_info_hash_and_pok(editor_public_key)
        url, container_signed, status, response = await self.put(
            editor_public_key=editor_public_key,
            editor_private_key=editor_private_key2,
            info_hash=info_hash,
            pok=pok,
            version=0,
            counter=1,
            expiration=int(2*time.time()),
            payload=randbytes(0)
        )

        self.assertEqual(status, 401)
        self.assertEqual(response, b'invalid signature')

    async def test_huge_payload(self):
        # All the arguments to the input
        editor_public_key, editor_private_key = self.editor_public_private_keys()
        info_hash, pok = self.generate_info_hash_and_pok(editor_public_key)

        # Put some data
        url, container_signed, status, response = await self.put(
            editor_public_key=editor_public_key,
            editor_private_key=editor_private_key,
            info_hash=info_hash,
            pok=pok,
            version=0,
            counter=0,
            expiration=int(time.time() + 100),
            # Put too much data
            payload=randbytes(257)
        )
        self.assertEqual(status, 413)
        self.assertEqual(response, b'payload cannot exceed 256 bytes')

    async def test_tiny_message(self):
        editor_public_key_base64 = base64.urlsafe_b64encode(randbytes(32)).decode()
        url = f'{URL_BASE}{editor_public_key_base64}'

        async with aiohttp.ClientSession() as session:
            # Put the data
            async with session.put(
                url,
                data=randbytes(100)) as response:

                self.assertEqual(response.status, 422)
                self.assertEqual(await response.read(), b'not enough data')

    async def test_version_nonzero(self):
        # All the arguments to the input
        editor_public_key, editor_private_key = self.editor_public_private_keys()
        info_hash, pok = self.generate_info_hash_and_pok(editor_public_key)

        # Put some data
        url, container_signed, status, response = await self.put(
            editor_public_key=editor_public_key,
            editor_private_key=editor_private_key,
            info_hash=info_hash,
            pok=pok,
            version=1,
            counter=0,
            expiration=int(time.time()),
            # Put too much data
            payload=randbytes(256)
        )
        self.assertEqual(status, 400)
        self.assertEqual(response, b'this is version zero')

    async def test_bad_url_encoding(self):
        editor_public_key_base64 = 'biq3wynGtSc_41Lc0n-yltuOVtJCjkkfX5znCPu56ns'
        url = f'{URL_BASE}{editor_public_key_base64}'

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                self.assertEqual(response.status, 422)
                self.assertEqual(await response.read(), b'public key is not correctly base 64 encoded')

    async def test_url_too_long(self):
        for byte_length in [31, 33]:
            editor_public_key_base64 = base64.urlsafe_b64encode(randbytes(byte_length)).decode()
            url = f'{URL_BASE}{editor_public_key_base64}'

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    self.assertEqual(response.status, 422)
                    self.assertEqual(await response.read(), b'public key must be exactly 32 bytes long')

    async def test_missing_link(self):
        editor_public_key_base64 = base64.urlsafe_b64encode(randbytes(32)).decode()
        url = f'{URL_BASE}{editor_public_key_base64}'

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                self.assertEqual(response.status, 404)
                self.assertEqual(await response.read(), b'link not found')

if __name__ == "__main__":
    unittest.main()