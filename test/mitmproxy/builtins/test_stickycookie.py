from .. import tutils, mastertest
from mitmproxy.builtins import stickycookie
from mitmproxy.flow import master
from mitmproxy.flow import state
from mitmproxy import options
from netlib import tutils as ntutils


def test_domain_match():
    assert stickycookie.domain_match("www.google.com", ".google.com")
    assert stickycookie.domain_match("google.com", ".google.com")


class TestStickyCookie(mastertest.MasterTest):
    def mk(self):
        s = state.State()
        m = master.FlowMaster(options.Options(stickycookie = ".*"), None, s)
        sc = stickycookie.StickyCookie()
        m.addons.add(sc)
        return s, m, sc

    def test_config(self):
        sc = stickycookie.StickyCookie()
        tutils.raises(
            "invalid filter",
            sc.configure,
            options.Options(stickycookie = "~b")
        )

    def test_simple(self):
        s, m, sc = self.mk()
        m.addons.add(sc)

        f = tutils.tflow(resp=True)
        f.response.headers["set-cookie"] = "foo=bar"
        self.invoke(m, "request", f)

        f.reply.acked = False
        self.invoke(m, "response", f)

        assert sc.jar
        assert "cookie" not in f.request.headers

        f = f.copy()
        f.reply.acked = False
        self.invoke(m, "request", f)
        assert f.request.headers["cookie"] == "foo=bar"

    def _response(self, s, m, sc, cookie, host):
        f = tutils.tflow(req=ntutils.treq(host=host, port=80), resp=True)
        f.response.headers["Set-Cookie"] = cookie
        self.invoke(m, "response", f)
        return f

    def test_response(self):
        s, m, sc = self.mk()

        c = "SSID=mooo; domain=.google.com, FOO=bar; Domain=.google.com; Path=/; " \
            "Expires=Wed, 13-Jan-2021 22:23:01 GMT; Secure; "

        self._response(s, m, sc, c, "host")
        assert not sc.jar.keys()

        self._response(s, m, sc, c, "www.google.com")
        assert sc.jar.keys()

        sc.jar.clear()
        self._response(
            s, m, sc, "SSID=mooo", "www.google.com"
        )
        assert list(sc.jar.keys())[0] == ('www.google.com', 80, '/')

    def test_response_multiple(self):
        s, m, sc = self.mk()

        # Test setting of multiple cookies
        c1 = "somecookie=test; Path=/"
        c2 = "othercookie=helloworld; Path=/"
        f = self._response(s, m, sc, c1, "www.google.com")
        f.response.headers["Set-Cookie"] = c2
        self.invoke(m, "response", f)
        googlekey = list(sc.jar.keys())[0]
        assert len(sc.jar[googlekey].keys()) == 2

    def test_response_weird(self):
        s, m, sc = self.mk()

        # Test setting of weird cookie keys
        f = tutils.tflow(req=ntutils.treq(host="www.google.com", port=80), resp=True)
        cs = [
            "foo/bar=hello",
            "foo:bar=world",
            "foo@bar=fizz",
            "foo,bar=buzz",
        ]
        for c in cs:
            f.response.headers["Set-Cookie"] = c
            self.invoke(m, "response", f)
        googlekey = list(sc.jar.keys())[0]
        assert len(sc.jar[googlekey].keys()) == len(cs)

    def test_response_overwrite(self):
        s, m, sc = self.mk()

        # Test overwriting of a cookie value
        c1 = "somecookie=helloworld; Path=/"
        c2 = "somecookie=newvalue; Path=/"
        f = self._response(s, m, sc, c1, "www.google.com")
        f.response.headers["Set-Cookie"] = c2
        self.invoke(m, "response", f)
        googlekey = list(sc.jar.keys())[0]
        assert len(sc.jar[googlekey].keys()) == 1
        assert list(sc.jar[googlekey]["somecookie"].items())[0][1] == "newvalue"

    def test_request(self):
        s, m, sc = self.mk()

        f = self._response(s, m, sc, "SSID=mooo", "www.google.com")
        assert "cookie" not in f.request.headers
        self.invoke(m, "request", f)
        assert "cookie" in f.request.headers