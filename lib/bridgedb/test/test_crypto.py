# -*- coding: utf-8 -*-
#
# This file is part of BridgeDB, a Tor bridge distribution system.
#
# :authors: Isis Lovecruft 0xA3ADB67A2CDB8B35 <isis@torproject.org>
#           please also see AUTHORS file
# :copyright: (c) 2013, Isis Lovecruft
#             (c) 2007-2013, The Tor Project, Inc.
#             (c) 2007-2013, all entities within the AUTHORS file
# :license: 3-Clause BSD, see LICENSE for licensing information

"""Unittests for :mod:`bridgedb.crypto`."""

from __future__ import print_function
from __future__ import unicode_literals

import gpgme
import io
import logging
import math
import os
import shutil

import OpenSSL

from twisted.internet import defer
from twisted.trial import unittest
from twisted.test.proto_helpers import StringTransport
from twisted.web.test import test_agent as txtagent

from bridgedb import crypto
from bridgedb import txrecaptcha
from bridgedb.persistent import Conf
from bridgedb.test.util import fileCheckDecorator


logging.disable(50)

SEKRIT_KEY  = b'v\x16Xm\xfc\x1b}\x063\x85\xaa\xa5\xf9\xad\x18\xb2P\x93\xc6k\xf9'
SEKRIT_KEY += b'\x8bI\xd9\xb8xw\xf5\xec\x1b\x7f\xa8'


class DummyEndpoint(object):
    """An endpoint that uses a fake transport."""

    def connect(self, factory):
        """Returns a connection to a
        :api:`twisted.test.proto_helpers.StringTransport`.
        """
        protocol = factory.buildProtocol(None)
        protocol.makeConnection(StringTransport())
        return defer.succeed(protocol)


class GetKeyTests(unittest.TestCase):
    """Tests for :func:`bridgedb.crypto.getKey`."""

    def test_getKey_nokey(self):
        """Test retrieving the secret_key from an empty file."""
        filename = os.path.join(os.getcwd(), 'sekrit')
        key = crypto.getKey(filename)
        self.failUnlessIsInstance(key, basestring,
                                  "key isn't a string! type=%r" % type(key))

    def test_getKey_tmpfile(self):
        """Test retrieving the secret_key from a new tmpfile."""
        filename = self.mktemp()
        key = crypto.getKey(filename)
        self.failUnlessIsInstance(key, basestring,
                                  "key isn't a string! type=%r" % type(key))

    def test_getKey_keyexists(self):
        """Write the example key to a file and test reading it back."""
        filename = self.mktemp()
        with open(filename, 'wb') as fh:
            fh.write(SEKRIT_KEY)
            fh.flush()

        key = crypto.getKey(filename)
        self.failUnlessIsInstance(key, basestring,
                                  "key isn't a string! type=%r" % type(key))
        self.assertEqual(SEKRIT_KEY, key,
                         """The example key and the one read from file differ!
                         key (in hex): %s
                         SEKRIT_KEY (in hex): %s"""
                         % (key.encode('hex'), SEKRIT_KEY.encode('hex')))


class LessCrypticGPGMEErrorTests(unittest.TestCase):
    """Unittests for :class:`bridgedb.crypto.LessCrypticGPGMEError`."""

    def test_error1(self):
        """libgpgme will raise an error when given an io.StringIO for the
        message or sigfile.
        """
        message = io.StringIO(unicode(self.id()))
        sigfile = io.StringIO()

        lessCryptic = None
        ctx = gpgme.Context()

        try:
            ctx.sign(message, sigfile)
        except gpgme.GpgmeError as error:
            lessCryptic = crypto.LessCrypticGPGMEError(error)

        self.assertTrue('Invalid argument' in lessCryptic.message)

    def test_noGpgmeErrorArgs(self):
        """A gpgme.GpgmeError() without error code args should result in a
        'Could not get error code from gpgme.GpgmeError!' message.
        """
        error = gpgme.GpgmeError()
        lessCryptic = crypto.LessCrypticGPGMEError(error)
        self.assertEqual(lessCryptic.message,
                         'Could not get error code from gpgme.GpgmeError!')

    def test_unknownErrorSource(self):
        """A gpgme.GpgmeError() without a recognisable error source should say
        that the error source is 'UNKNOWN'.
        """
        msg = "These numbers make more sense than libgpgme's error codes."
        error = gpgme.GpgmeError(math.pi, math.e, msg)
        lessCryptic = crypto.LessCrypticGPGMEError(error)
        self.assertSubstring('UNKNOWN', lessCryptic.message)
        self.assertSubstring(msg, lessCryptic.message)

    def test_unknownErrorCode(self):
        """A gpgme.GpgmeError() without a recognisable error code should say
        that the error code is 'UNKNOWN'.
        """
        msg = "These numbers make more sense than libgpgme's error codes."
        error = gpgme.GpgmeError(math.pi, math.e, msg)
        lessCryptic = crypto.LessCrypticGPGMEError(error)
        self.assertSubstring('UNKNOWN', lessCryptic.message)
        self.assertSubstring(msg, lessCryptic.message)


class GPGContextTests(unittest.TestCase):
    """Tests for :func:`bridgedb.crypto.getGPGContext`."""

    timeout = 15

    @fileCheckDecorator
    def doCopyFile(self, src, dst, description=None):
        shutil.copy(src, dst)

    def removeRundir(self):
        """Remove the rundir from the _trial_tmp directory."""
        if os.path.isdir(self.runDir):
            shutil.rmtree(self.runDir)

    def makeBadKey(self):
        """Make a bad keyfile and set its path in our config."""
        keyfile = os.path.join(self.runDir, 'badkey.asc')
        with open(keyfile, 'w') as badkey:
            badkey.write(str('NO PASARAN, DEATH CAKES!'))
            badkey.flush()
        self.setKey(keyfile)

    def enableSigning(self, enable=True):
        """Enable or disable the config setting for email signing."""
        setattr(self.config, 'EMAIL_GPG_SIGNING_ENABLED', enable)

    def setKey(self, keyfile=''):
        """Set the config keyfile path to **keyfile**."""
        setattr(self.config, 'EMAIL_GPG_SIGNING_KEY', keyfile)

    def setUp(self):
        here          = os.getcwd()
        topDir        = here.rstrip('_trial_temp')
        self.runDir   = os.path.join(here, 'rundir')
        self.gpgFile  = os.path.join(topDir, 'gnupghome', 'TESTING.subkeys.sec')
        self.gpgExpr  = os.path.join(topDir, 'gnupghome',
                                     'TESTING.subkeys.sec.EXPIRED-2013-09-11')

        if not os.path.isdir(self.runDir):
            os.makedirs(self.runDir)

        self.config = Conf()
        self.enableSigning()
        self.addCleanup(self.enableSigning)
        self.addCleanup(self.removeRundir)

    def test_getGPGContext_good_keyfile(self):
        """Test EmailServer.getGPGContext() with a good key filename."""
        self.setKey(self.gpgFile)
        ctx = crypto.getGPGContext(self.config)
        self.assertIsInstance(ctx, gpgme.Context)

    def test_getGPGContext_missing_keyfile(self):
        """Test EmailServer.getGPGContext() with a missing key filename."""
        self.setKey('missing-keyfile.asc')
        ctx = crypto.getGPGContext(self.config)
        self.assertTrue(ctx is None)

    def test_getGPGContext_bad_keyfile(self):
        """Test EmailServer.getGPGContext() with a missing key filename."""
        self.makeBadKey()
        ctx = crypto.getGPGContext(self.config)
        self.assertTrue(ctx is None)

    def test_getGPGContext_expired_keyfile(self):
        """getGPGContext() with an expired key should return None."""
        self.setKey(self.gpgExpr)
        ctx = crypto.getGPGContext(self.config)
        self.assertTrue(ctx is None)

    def test_getGPGContext_signing_disabled(self):
        """getGPGContext() with signing disabled should return None."""
        self.setKey(self.gpgFile)
        self.enableSigning(False)
        ctx = crypto.getGPGContext(self.config)
        self.assertIsNone(ctx)

    def test_getGPGContext_config_signing_missing(self):
        """getGPGContext() with a missing/unset 'EMAIL_GPG_SIGNING_ENABLED'
        config line should return None.
        """
        self.setKey(self.gpgFile)
        delattr(self.config, 'EMAIL_GPG_SIGNING_ENABLED')
        ctx = crypto.getGPGContext(self.config)
        self.assertIsNone(ctx)


class SSLVerifyingContextFactoryTests(unittest.TestCase,
                                      txtagent.FakeReactorAndConnectMixin):
    """Tests for :class:`bridgedb.crypto.SSLVerifyingContextFactory`."""

    _certificateText = (
        "-----BEGIN CERTIFICATE-----\n"
        "MIIEdjCCA16gAwIBAgIITcyHZlE/AhQwDQYJKoZIhvcNAQEFBQAwSTELMAkGA1UE\n"
        "BhMCVVMxEzARBgNVBAoTCkdvb2dsZSBJbmMxJTAjBgNVBAMTHEdvb2dsZSBJbnRl\n"
        "cm5ldCBBdXRob3JpdHkgRzIwHhcNMTQwMjEyMTUxMTE2WhcNMTQwNjEyMDAwMDAw\n"
        "WjBoMQswCQYDVQQGEwJVUzETMBEGA1UECAwKQ2FsaWZvcm5pYTEWMBQGA1UEBwwN\n"
        "TW91bnRhaW4gVmlldzETMBEGA1UECgwKR29vZ2xlIEluYzEXMBUGA1UEAwwOd3d3\n"
        "Lmdvb2dsZS5jb20wggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQCt3TOf\n"
        "VOf4vfy4IROcEyiFzAJA+B3xkMccwA4anaD6VyGSFglRn5Oht3t+G0Mnu/LMuGba\n"
        "EE6NEBEUEbH8KMlAcVRj58LoFIzulaRCdkVX7JK9R+kU05sggvIl1Q2quaWSjiMQ\n"
        "SpyvKz1I2cmU5Gm4MfW/66M5ZJO323VrV19ydrgAtdbNnvVj85asrSyzwEBNxzNC\n"
        "N6OQtOmTt4I7KLXqkROtTmTFvhAGBsvhG0hJZWhoP1aVsFO+KcE2OaIIxWQ4ckW7\n"
        "BJEgYaXfgHo01LdR55aevGUqLfsdyT+GMZrG9k7eqAw4cq3ML2Y6RiyzskqoQL30\n"
        "3OdYjKTIcU+i3BoFAgMBAAGjggFBMIIBPTAdBgNVHSUEFjAUBggrBgEFBQcDAQYI\n"
        "KwYBBQUHAwIwGQYDVR0RBBIwEIIOd3d3Lmdvb2dsZS5jb20waAYIKwYBBQUHAQEE\n"
        "XDBaMCsGCCsGAQUFBzAChh9odHRwOi8vcGtpLmdvb2dsZS5jb20vR0lBRzIuY3J0\n"
        "MCsGCCsGAQUFBzABhh9odHRwOi8vY2xpZW50czEuZ29vZ2xlLmNvbS9vY3NwMB0G\n"
        "A1UdDgQWBBQN7uQBzGDjvKRna111g9iPPtaXVTAMBgNVHRMBAf8EAjAAMB8GA1Ud\n"
        "IwQYMBaAFErdBhYbvPZotXb1gba7Yhq6WoEvMBcGA1UdIAQQMA4wDAYKKwYBBAHW\n"
        "eQIFATAwBgNVHR8EKTAnMCWgI6Ahhh9odHRwOi8vcGtpLmdvb2dsZS5jb20vR0lB\n"
        "RzIuY3JsMA0GCSqGSIb3DQEBBQUAA4IBAQBrVp/xys2ABQvWPxpVrYaXiaoBXdxu\n"
        "RVVXp5Lyu8IipKqFJli81hOX9eqPG7biYeph9HiKnW31xsXebaVlWWL3NXOh5X83\n"
        "wpzozL0AkxskTMHQknrbIGLtmG67H71aKYyCthHEjawLmYjjvkcF6f9fKdYENM4C\n"
        "skz/yjtlPBQFAuT6J9w0b3qtc42sHNlpgIOdIRQc2YCD0p6jAo+wKjoRuRu3ILKj\n"
        "oCVrOPbDMPN4a2gSmK8Ur0aHuEpcNghg6HJsVSANokIIwQ/r4niqL5yotsangP/5\n"
        "rR97EIYKFz7C6LMy/PIe8xFTIyKMtM59IcpUDIwCLlM9JtNdwN4VpyKy\n"
        "-----END CERTIFICATE-----\n")

    def setUp(self):
        """Create a fake reactor for these tests."""
        self.reactor = self.Reactor()
        self.url = 'https://www.example.com/someresource.html#andatag'

    def test_getHostnameFromURL(self):
        """``getHostnameFromURL()`` should return a hostname from a URI."""
        agent = txrecaptcha._getAgent(self.reactor, self.url)
        contextFactory = agent._contextFactory
        self.assertRegexpMatches(contextFactory.hostname,
                                 '.*www\.example\.com')

    def test_verifyHostname_mismatching(self):
        """Check that ``verifyHostname()`` returns ``False`` when the
        ``SSLVerifyingContextFactory.hostname`` does not match the one found
        in the level 0 certificate subject CN.
        """
        agent = txrecaptcha._getAgent(self.reactor, self.url)
        contextFactory = agent._contextFactory
        x509 = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM,
                                               self._certificateText)
        conn = DummyEndpoint()
        result = contextFactory.verifyHostname(conn, x509, 0, 0, True)
        self.assertIs(result, False)

    def test_verifyHostname_matching(self):
        """Check that ``verifyHostname()`` returns ``True`` when the
        ``SSLVerifyingContextFactory.hostname`` matches the one found in the
        level 0 certificate subject CN.
        """
        hostname = 'www.google.com'
        url = 'https://' + hostname + '/recaptcha'
        contextFactory = crypto.SSLVerifyingContextFactory(url)
        self.assertEqual(contextFactory.hostname, hostname)

        x509 = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM,
                                               self._certificateText)
        conn = DummyEndpoint()
        result = contextFactory.verifyHostname(conn, x509, 0, 0, True)
        self.assertTrue(result)

    def test_getContext(self):
        """The context factory's ``getContext()`` method should produce an
        ``OpenSSL.SSL.Context`` object.
        """
        contextFactory = crypto.SSLVerifyingContextFactory(self.url)
        self.assertIsInstance(contextFactory.getContext(),
                              OpenSSL.SSL.Context)


class GetGPGContextTest(unittest.TestCase):
    """Unittests for :func:`bridgedb.crypto.getGPGContext`."""

    timeout = 15

    @fileCheckDecorator
    def doCopyFile(self, src, dst, description=None):
        shutil.copy(src, dst)

    def removeRundir(self):
        if os.path.isdir(self.runDir):
            shutil.rmtree(self.runDir)

    def makeBadKey(self):
        self.setKey(self.badKeyfile)

    def setKey(self, keyfile=''):
        setattr(self.config, 'EMAIL_GPG_SIGNING_KEY', keyfile)

    def setUp(self):
        here          = os.getcwd()
        topDir        = here.rstrip('_trial_temp')
        self.runDir   = os.path.join(here, 'rundir')
        self.gpgMoved = os.path.join(here, 'TESTING.subkeys.sec')
        self.gpgFile  = os.path.join(topDir, 'gnupghome',
                                     'TESTING.subkeys.sec')

        if not os.path.isdir(self.runDir):
            os.makedirs(self.runDir)

        self.badKeyfile = os.path.join(here, 'badkey.asc')
        with open(self.badKeyfile, 'w') as badkey:
            badkey.write('NO PASARAN, DEATH CAKES!')
            badkey.flush()

        self.doCopyFile(self.gpgFile, self.gpgMoved, "GnuPG test keyfile")

        self.config = Conf()
        setattr(self.config, 'EMAIL_GPG_SIGNING_ENABLED', True)
        setattr(self.config, 'EMAIL_GPG_SIGNING_KEY',
                'gnupghome/TESTING.subkeys.sec')

        self.addCleanup(self.removeRundir)

    def test_getGPGContext_good_keyfile(self):
        """Test EmailServer.getGPGContext() with a good key filename."""
        self.setKey(self.gpgMoved)
        ctx = crypto.getGPGContext(self.config)
        self.assertIsInstance(ctx, crypto.gpgme.Context)

    def test_getGPGContext_missing_keyfile(self):
        """Test EmailServer.getGPGContext() with a missing key filename."""
        self.setKey('missing-keyfile.asc')
        ctx = crypto.getGPGContext(self.config)
        self.assertTrue(ctx is None)

    def test_getGPGContext_bad_keyfile(self):
        """Test EmailServer.getGPGContext() with a missing key filename."""
        self.makeBadKey()
        ctx = crypto.getGPGContext(self.config)
        self.assertTrue(ctx is None)
