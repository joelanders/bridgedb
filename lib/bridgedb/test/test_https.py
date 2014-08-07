#_____________________________________________________________________________
#
# This file is part of BridgeDB, a Tor bridge distribution system.
#
# :authors: trygve <tor-dev@lists.torproject.org>
# :copyright: (c) trygve
#             (c) 2014, The Tor Project, Inc.
# :license: see LICENSE for licensing information
#_____________________________________________________________________________
"""integration tests for BridgeDB .
http://wwwsearch.sourceforge.net/mechanize/
http://www.crummy.com/software/BeautifulSoup/bs3/documentation.html
"""

from __future__ import print_function
from twisted.trial import unittest
from BeautifulSoup import BeautifulSoup
import mechanize

HTTPS_ROOT = 'https://127.0.0.1:6789'
CAPTCHA_RESPONSE = 'Tvx74Pmy'

class HTTPTests(unittest.TestCase):
    def setUp(self):
	self.br = None

    def tearDown(self):
	self.br = None

    def openBrowser(self):
	# use mechanize to open the BridgeDB website in its browser
	self.br = mechanize.Browser()
	self.br.set_handle_robots(False) # prevents 'HTTP Error 403: request disallowed by robots.txt'
	self.br.open(HTTPS_ROOT)

	# -------------- Home/Root  page
	self.assertTrue(self.br.viewing_html())
	self.assertEquals(self.br.response().geturl(), HTTPS_ROOT)
	self.assertEquals(self.br.title(), "BridgeDB")
	#for link in self.br.links(): print(link)
	#for form in self.br.forms(): print(form)
	return self.br

    def goToOptionsPage(self):
        # check that we are on the root page
	self.assertTrue(self.br.viewing_html())
	self.assertEquals(self.br.response().geturl(), HTTPS_ROOT)

	# follow the link with the word 'bridges' in it.
	# Could also use: text='bridges'
	# Could also use: url='/options'
	self.br.follow_link(text_regex='bridges')

	# ------------- Options
	self.assertEquals(self.br.response().geturl(), HTTPS_ROOT + "/options")
	#print(self.br.response().read())
	#for form in self.br.forms(): print(form)
	return self.br
     
    def submitOptions(self, transport, ipv6, captchaResponse):
	# check that we are on the options page
	self.assertEquals(self.br.response().geturl(), HTTPS_ROOT + "/options")

	# At this point, we'd like to be able to set some values in
	# the 'advancedOptions' form. Unfortunately the HTML form
	# does not define a 'name' attribute, so the we have to rely on
	# the fact that this is the only form on the page and will therefore
	# always exist at index 0.
	#br.select_form(name="advancedOptions")
	self.br.select_form(nr=0)

	# change the pluggable transport to something else 
	#print(self.br.form)
	self.br.form['transport'] = [transport]
        if ipv6:
            self.br.form['ipv6'] = ['yes']
	self.br.submit()

	# ------------- Captcha
	EXPECTED_URL = HTTPS_ROOT + "/bridges?transport=%s" % transport
        if ipv6:
            EXPECTED_URL += "&ipv6=yes"
	self.assertEquals(self.br.response().geturl(), EXPECTED_URL)
	#print(self.br.response().read())
	#for form in self.br.forms(): print(form)

	# As on the previous page, the form does not define a 'name' attribute, forcing 
	# us to use the index of the form i.e. 0
	#self.br.select_form(name="captchaSubmission")
	self.br.select_form(nr=0)

	# input the required captcha response. There is only one captcha defined
	# by default, so this should always be accepted. Note this will not be possible
	# to automate if used with a real captcha systems (e.g. reCAPTCHA)
	#self.br.form['captcha_response_field'] = 'Tvx74PMy'
	self.br.form['captcha_response_field'] = captchaResponse
	captcha_response = self.br.submit()

	# ------------- Results
	# URL should be the same as last time
	self.assertEquals(self.br.response().geturl(), EXPECTED_URL)
	soup = BeautifulSoup(captcha_response.read())
	#print soup.prettify()
	return soup

    def getBridgeLinesFromSoup(self, soup):
	# Now we're looking for something like this in the response:
	#     <div class="bridge-lines">
	#      obfs2 175.213.252.207:11125 5c6da7d927460317c6ff5420b75c2d0f431f18dd
	#     </div>
	bridges = []
	bridge_lines = soup.findAll(attrs={'class' : 'bridge-lines'})
	self.assertTrue(len(bridge_lines) > 0, "Found no bridge lines")
	for bridge_line in bridge_lines:
	    text = bridge_line.text
	    #print("Found bridge-line: %s" % text)
	    items = text.split(' ')
   	    self.assertEquals(len(items), 3, "Expected Pluggale Transport, Bridge and Fingerprint in %s" % str(items))
	    bridges.append(items)
	return bridges

    def test_get_obfs2_ipv4(self):
	self.openBrowser()
	self.goToOptionsPage()

	PT = 'obfs2'
        soup = self.submitOptions(transport=PT, ipv6=False, captchaResponse=CAPTCHA_RESPONSE)

	bridges = self.getBridgeLinesFromSoup(soup)
        for pt, bridge, fingerprint in bridges:
	    self.assertEquals(PT, pt)

    def test_get_obfs3_ipv4(self):
	self.openBrowser()
	self.goToOptionsPage()

	PT = 'obfs3'
        soup = self.submitOptions(transport=PT, ipv6=False, captchaResponse=CAPTCHA_RESPONSE)

	bridges = self.getBridgeLinesFromSoup(soup)
        for pt, bridge, fingerprint in bridges:
	    self.assertEquals(PT, pt)

    def test_get_obfs3_ipv6(self):
	self.openBrowser()
	self.goToOptionsPage()

	PT = 'obfs3'
        soup = self.submitOptions(transport=PT, ipv6=True, captchaResponse=CAPTCHA_RESPONSE)

	# at the time of writing, this test fails due to lack of ipv6 bridges
	bridges = self.getBridgeLinesFromSoup(soup)
        for pt, bridge, fingerprint in bridges:
	    self.assertEquals(PT, pt)
