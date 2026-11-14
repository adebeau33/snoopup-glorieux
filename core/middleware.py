import ipaddress
class ClientIPMiddleware:
 def __init__(self,get_response):self.get_response=get_response
 def __call__(self,request):
  # Only Apache on loopback is trusted; it overwrites this header.
  if request.META.get('REMOTE_ADDR') in ['127.0.0.1','::1']:
   try:request.META['REMOTE_ADDR']=str(ipaddress.ip_address(request.META.get('HTTP_X_REAL_IP','')))
   except ValueError:pass
  return self.get_response(request)
