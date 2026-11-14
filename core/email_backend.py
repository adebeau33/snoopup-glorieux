from django.core.mail.backends.base import BaseEmailBackend
from .delivery import send_email
class SESBackend(BaseEmailBackend):
 def send_messages(self,email_messages):
  count=0
  for message in email_messages:
   for recipient in message.to:
    send_email(recipient,message.subject,message.body);count+=1
  return count
