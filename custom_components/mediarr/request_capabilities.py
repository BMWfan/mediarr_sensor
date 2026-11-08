"""Read-only Seerr/default manager probes for request button availability."""
import asyncio
import time
import aiohttp
from homeassistant.components import websocket_api


class ProbeFailure(Exception):
    pass


async def read(handler, path, reason):
    try:
        async with handler._session.get(handler._url + '/api/v1/' + path,
                headers=handler._headers, allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=5)) as response:
            if response.status != 200:
                raise ProbeFailure('seer_auth' if response.status in (401,403) else reason)
            return await response.json()
    except (aiohttp.ClientError, TimeoutError, ValueError):
        raise ProbeFailure(reason) from None


async def probe(handler, kind):
    provider='radarr' if kind=='movie' else 'sonarr'
    try:
        await read(handler,'auth/me','seer_unavailable')
        servers=await read(handler,'service/'+provider,'seer_unavailable')
        if not isinstance(servers,list):
            raise ProbeFailure(provider+'_configuration')
        server=next((s for s in servers if isinstance(s,dict) and s.get('isDefault') is True and not s.get('is4k')),None)
        if not server or type(server.get('id')) is not int or server['id']<0:
            raise ProbeFailure(provider+'_configuration')
        details=await read(handler,f"service/{provider}/{server['id']}",provider+'_unavailable')
        configured=details.get('server',{})
        if not configured.get('activeDirectory') or not any(p.get('id')==configured.get('activeProfileId') for p in details.get('profiles',[])) or not any(f.get('path')==configured['activeDirectory'] for f in details.get('rootFolders',[])):
            raise ProbeFailure(provider+'_configuration')
        return {'available':True,'reason':'ready'}
    except ProbeFailure as error:
        return {'available':False,'reason':str(error)}
    except (AttributeError,KeyError,TypeError):
        return {'available':False,'reason':provider+'_configuration'}


async def metadata_probe(data, account=False):
    client=data.get('metadata_client')
    if not client:
        return {'available':False,'reason':'tmdb_not_configured'}
    if account:
        from .cinema import tmdb_application_token
        key=tmdb_application_token(data)
    else:
        key=client.key_resolver()
    if not key:
        return {'available':False,'reason':'tmdb_not_configured'}
    try:
        await asyncio.wait_for(client._get('configuration',key,'en'),timeout=5)
        return {'available':True,'reason':'ready'}
    except Exception:
        return {'available':False,'reason':'tmdb_unavailable'}


async def immaculaterr_probe(handler):
    if not handler:return {'available':False,'reason':'immaculaterr_not_configured'}
    try:
        await asyncio.wait_for(handler._client.async_list_rejected(),timeout=5)
        return {'available':True,'reason':'ready'}
    except Exception:
        return {'available':False,'reason':'immaculaterr_unavailable'}


async def capabilities(hass):
    data=hass.data.get('mediarr',{})
    handler=data.get('seer_request_handler')
    immaculate=data.get('immaculaterr_request_handler')
    owners=(handler,immaculate,data.get('metadata_client'))
    def cached_result():
        cached=data.get('request_capabilities_cache')
        return cached[2] if cached and all(a is b for a,b in zip(cached[0],owners)) and time.monotonic()-cached[1]<10 else None
    cached=cached_result()
    if cached is not None:return cached
    lock=data.setdefault('request_capabilities_lock',asyncio.Lock())
    async with lock:
        cached=cached_result()
        if cached is not None:return cached
        async def manager(kind):
            return await probe(handler,kind) if handler else {'available':False,'reason':'seer_not_configured'}
        values=await asyncio.gather(manager('movie'),manager('tv'),immaculaterr_probe(immaculate),metadata_probe(data),metadata_probe(data,True))
        result=dict(zip(('movie','tv','immaculaterr','tmdb','tmdb_account'),values))
        data['request_capabilities_cache']=(owners,time.monotonic(),result)
        return result


@websocket_api.websocket_command({'type':'mediarr/request_capabilities'})
@websocket_api.async_response
async def websocket_request_capabilities(hass,connection,msg):
    connection.send_result(msg['id'],await capabilities(hass))


def async_setup_request_capabilities(hass):
    websocket_api.async_register_command(hass,websocket_request_capabilities)
