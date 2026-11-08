"""Run with HA installed: python -m unittest discover -s tests."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('media_details',Path(__file__).parents[1]/'custom_components/mediarr/media_details.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Response:
    def __init__(self,data,status=200):self.data=data;self.status=status
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    async def json(self):return self.data

class Session:
    def __init__(self,responses):self.responses=list(responses);self.calls=[]
    def get(self,url,**kwargs):
        self.calls.append((url,kwargs))
        return self.responses.pop(0)

DETAIL={'id':7,'name':'Dark','first_air_date':'2017-12-01','overview':'Full plot','genres':[{'name':'Mystery'}],'credits':{'cast':[{'name':'Actor','character':'Pilot','profile_path':'/actor.jpg'}],'crew':[{'name':'Director','job':'Director'}]},'external_ids':{'tvdb_id':12},'vote_average':8.2}

class MetadataTests(unittest.IsolatedAsyncioTestCase):
    def test_trailers_require_official_youtube_ids_and_prefer_user_language(self):
        video=lambda **extra: {"site":"YouTube","type":"Trailer","official":True,"key":"abcdef12345","iso_639_1":"en",**extra}
        data={"videos":{"results":[video(),video(iso_639_1="de",key="german12345"),video(key="../../bad"),video(official=False)]}}
        self.assertEqual(m.public_trailer(data,"de-DE")["url"],"https://www.youtube.com/watch?v=german12345")
        self.assertIsNone(m.public_trailer({"videos":{"results":[video(type="Clip"),video(site="untrusted"),video(key="bad"),video(official=False)]}},"de"))

    def test_streaming_region_and_subscription_rental_separation(self):
        data={'watch/providers':{'results':{'DE':{'flatrate':[{'provider_id':8,'provider_name':'Netflix'}],
            'rent':[{'provider_id':10,'provider_name':'Amazon Video'}],
            'link':'https://www.themoviedb.org/movie/1/watch'},'US':{'flatrate':[{'provider_name':'Other'}]}}}}
        offers=m.public_streaming(data,'DE')
        self.assertEqual(offers['subscription'][0]['name'],'Netflix')
        self.assertEqual(offers['rent'][0]['name'],'Amazon Video')
        self.assertEqual(offers['buy'],[])
        self.assertEqual(m.public_streaming(data,'FR')['subscription'],[])

    async def test_catalog_search_filters_people_adult_and_invalid_ids_and_caches(self):
        data={'total_pages':12,'results':[
            {'id':7,'media_type':'tv','name':'Dark','first_air_date':'2017-01-01'},
            {'id':7,'media_type':'movie','title':'Dark'},
            {'id':8,'media_type':'person','name':'An actor'},
            {'id':9,'media_type':'movie','title':'Adult','adult':True},
            {'id':True,'media_type':'movie','title':'Invalid'}]}
        session=Session([Response(data)])
        client=m.MediaDetailsClient(session,lambda:'test-fixture-key')
        result=await client.search(query='Dark',language='de')
        self.assertEqual([(x['media_type'],x['tmdb_id']) for x in result['results']],[('tv',7),('movie',7)])
        self.assertEqual(result['total_pages'],5)
        self.assertEqual(await client.search(query='Dark',language='de'),result)
        self.assertEqual(len(session.calls),1)
        self.assertEqual(session.calls[0][1]['params']['include_adult'],'false')
        self.assertNotIn('test-fixture',str(result))

    async def test_catalog_validation_and_pagination(self):
        client=m.MediaDetailsClient(Session([]),lambda:'test-fixture-key')
        for args in [{'query':'x'},{'query':'x'*129},{'query':'valid','page':True},{'query':'valid','page':6},{'query':'valid','language':'../bad'}]:
            with self.assertRaises(m.MediaDetailsError):await client.search(**args)
        client=m.MediaDetailsClient(Session([]),lambda:None)
        with self.assertRaises(m.MediaDetailsError) as error:await client.search(query='valid')
        self.assertEqual(error.exception.code,'tmdb_not_configured')
        session=Session([Response({'results':[],'total_pages':2})])
        client=m.MediaDetailsClient(session,lambda:'test-fixture-key')
        self.assertEqual((await client.search(query='valid',page=2))['page'],2)
        self.assertEqual(session.calls[0][1]['params']['page'],2)

    def test_catalog_websocket_schema(self):
        schema=m.websocket_media_search._ws_schema
        self.assertEqual(schema({'id':1,'type':'mediarr/search','query':'Dark'})['page'],1)
        with self.assertRaises(Exception):schema({'id':1,'type':'mediarr/search','query':'x'})

    async def test_details_and_cache_do_not_expose_credentials(self):
        session=Session([Response(DETAIL)])
        client=m.MediaDetailsClient(session,lambda:'test-fixture-not-a-real-credential')
        result=await client.details(media_type='tv',tmdb_id=7,language='de')
        again=await client.details(media_type='tv',tmdb_id=7,language='de')
        self.assertEqual(result,again);self.assertEqual(len(session.calls),1)
        self.assertEqual(result['cast'][0]['character'],'Pilot');self.assertEqual(result['year'],'2017')
        self.assertNotIn('test-fixture',str(result));self.assertIn('credits,external_ids',session.calls[0][1]['params']['append_to_response'])

    async def test_title_search_uses_correct_type_not_first_result(self):
        session=Session([Response({'results':[{'id':1,'title':'Other'},{'id':7,'name':'Dark','first_air_date':'2017-12-01'}]}),Response(DETAIL)])
        client=m.MediaDetailsClient(session,lambda:'test-fixture-key')
        result=await client.details(media_type='tv',title='Dark',year=2017)
        self.assertEqual(result['tmdb_id'],7);self.assertTrue(session.calls[0][0].endswith('/search/tv'))

    async def test_ambiguous_film_series_is_not_guessed(self):
        session=Session([Response({'results':[{'id':1,'title':'Same','media_type':'movie'},{'id':2,'name':'Same','media_type':'tv'}]})])
        client=m.MediaDetailsClient(session,lambda:'test-fixture-key')
        with self.assertRaises(m.MediaDetailsError) as error:await client.details(title='Same')
        self.assertEqual(error.exception.code,'metadata_ambiguous');self.assertEqual(len(session.calls),1)

    async def test_missing_key_and_invalid_input_do_not_make_requests(self):
        session=Session([]);client=m.MediaDetailsClient(session,lambda:None)
        with self.assertRaises(m.MediaDetailsError) as error:await client.details(media_type='movie',tmdb_id=1)
        self.assertEqual(error.exception.code,'tmdb_not_configured')
        for kwargs in [{'media_type':'../../private','tmdb_id':1},{'media_type':'movie','tmdb_id':True},{'title':'x','language':'../bad'},{'title':'x','year':True}]:
            with self.assertRaises(m.MediaDetailsError):await client.details(**kwargs)
        self.assertEqual(session.calls,[])

    async def test_rejected_auth_error_is_safe(self):
        session=Session([Response({},401)]);client=m.MediaDetailsClient(session,lambda:'test-fixture-key')
        with self.assertRaises(m.MediaDetailsError) as error:await client.details(media_type='movie',tmdb_id=7)
        self.assertEqual(error.exception.code,'metadata_auth');self.assertNotIn('test-fixture-key',str(error.exception))

    def test_key_resolver_never_uses_unrelated_api_key(self):
        self.assertIsNone(m.resolve_tmdb_key({'entries':{'x':{'seer':{'api_key':'not-a-tmdb-key'}}}}))
        self.assertEqual(m.resolve_tmdb_key({'entries':{'x':{'plex':{'tmdb_api_key':'tmdb-fixture'}}}}),'tmdb-fixture')

    def test_websocket_command_uses_actual_homeassistant_decorator(self):
        self.assertEqual(m.websocket_media_details._ws_command,'mediarr/media_details')
        schema=m.websocket_media_details._ws_schema
        parsed=schema({'id':1,'type':'mediarr/media_details','media_type':'tv','tmdb_id':7,'title':'Dark','language':'de'})
        self.assertEqual(parsed['tmdb_id'],7)
        with self.assertRaises(Exception):schema({'id':2,'type':'mediarr/media_details','unexpected':'not accepted'})

if __name__=='__main__':unittest.main()
