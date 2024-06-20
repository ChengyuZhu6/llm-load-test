import os

def set_proxy(proxies: dict):
    if len(proxies) == 0:
        for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
            os.environ.pop(var, None)
    else:
        for key,value in proxies.items():
            os.environ[key] = value