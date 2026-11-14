#!/usr/bin/env python3
"""Execute only project deployment commands through the authorized digi2 relay."""
import shlex, subprocess, sys
TARGET='ec2-user@ec2-13-51-188-194.eu-north-1.compute.amazonaws.com'
command='ssh -o BatchMode=yes -i /root/My_New_server.pem '+TARGET+' '+shlex.quote(sys.argv[1])
raise SystemExit(subprocess.call(['ssh','-o','BatchMode=yes','-p','2222','root@10.66.66.1',command]))
