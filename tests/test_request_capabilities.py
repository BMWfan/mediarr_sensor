import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from custom_components.mediarr.request_capabilities import capabilities


class Response:
    def __init__(self,status,data):self.status,self.data=status,data
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    async def json(self):return self.data


class Session:
    def __init__(self):self.calls=[];self.fail=None;self.auth=200;self.default=True;self.valid=True
    def get(self,url,**kwargs):
        self.calls.append((url,kwargs))
        if url.endswith('/auth/me'):return Response(self.auth,{'id':1})
        if url.endswith(('/radarr','/sonarr')):return Response(200,[{'id':0,'isDefault':self.default,'is4k':False}])
        if self.fail and self.fail in url:return Response(503,{})
        return Response(200,{'server':{'activeProfileId':1,'activeDirectory':'/media','apiKey':'never-expose'},'profiles':[{'id':1}],'rootFolders':[{'path':'/media' if self.valid else '/other'}]})


class CapabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_optional_tool_connections_follow_real_read_result(self):
        metadata=SimpleNamespace(key_resolver=lambda:'key',_get=AsyncMock(return_value={}))
        client=SimpleNamespace(async_list_rejected=AsyncMock(return_value={}))
        hass=SimpleNamespace(data={'mediarr':{'metadata_client':metadata,'immaculaterr_request_handler':SimpleNamespace(_client=client)}})
        result=await capabilities(hass)
        self.assertTrue(result['tmdb']['available']);self.assertTrue(result['immaculaterr']['available'])
        hass.data['mediarr'].pop('request_capabilities_cache')
        metadata._get.side_effect=RuntimeError('offline');client.async_list_rejected.side_effect=RuntimeError('offline')
        result=await capabilities(hass)
        self.assertFalse(result['tmdb']['available']);self.assertFalse(result['immaculaterr']['available'])

    def setup_hass(self):
        session=Session()
        handler=SimpleNamespace(_url='https://seer.invalid',_headers={'X-Api-Key':'secret'},_session=session)
        return SimpleNamespace(data={'mediarr':{'seer_request_handler':handler}}),session

    async def test_ready_probes_use_read_only_service_routes_and_cache(self):
        hass,session=self.setup_hass()
        result=await capabilities(hass)
        self.assertTrue(result['movie']['available']);self.assertTrue(result['tv']['available'])
        self.assertEqual(len(session.calls),6)
        self.assertNotIn('never-expose',str(result));self.assertNotIn('secret',str(result));self.assertNotIn('/media',str(result))
        self.assertEqual(await capabilities(hass),result);self.assertEqual(len(session.calls),6)
        self.assertTrue(all(kwargs['allow_redirects'] is False for _,kwargs in session.calls))

    async def test_radarr_failure_disables_movie_but_not_series(self):
        hass,session=self.setup_hass();session.fail='/radarr/0'
        result=await capabilities(hass)
        self.assertEqual(result['movie'],{'available':False,'reason':'radarr_unavailable'})
        self.assertTrue(result['tv']['available'])

    async def test_auth_missing_default_and_bad_root_disable_requests(self):
        for field,value,reason in [('auth',401,'seer_auth'),('default',False,'radarr_configuration'),('valid',False,'radarr_configuration')]:
            hass,session=self.setup_hass();setattr(session,field,value)
            self.assertEqual((await capabilities(hass))['movie'],{'available':False,'reason':reason})

    async def test_missing_handler_and_configuration_change(self):
        self.assertFalse((await capabilities(SimpleNamespace(data={})))['movie']['available'])
        hass,session=self.setup_hass();await capabilities(hass)
        replacement=Session();replacement.auth=401
        hass.data['mediarr']['seer_request_handler']=SimpleNamespace(_url='https://other.invalid',_headers={},_session=replacement)
        self.assertEqual((await capabilities(hass))['movie']['reason'],'seer_auth')
