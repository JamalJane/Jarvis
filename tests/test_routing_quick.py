from jarvis.lib import _classify_google, _email_sub
tests = [
    ('send an email to basheirkhalid2011@Gmail.com', 'email', 'send'),
    ('Hey jarvis send an email to basheirkhalid2011@Gmail.com', 'email', 'send'),
    ('email bob saying hi', 'email', 'send'),
    ('check my inbox', 'email', 'read'),
    ('check my email', 'email', 'read'),
    ('what emails do I have', 'email', 'read'),
    ('check my calendar', 'calendar', None),
    ('any meetings today', 'calendar', None),
    ('create a doc', 'doc', None),
    ('open youtube', '', None),
]
all_ok = True
for q, exp_intent, exp_sub in tests:
    got_intent = _classify_google(q)
    got_sub = _email_sub(q) if got_intent == 'email' else None
    ok = got_intent == exp_intent and got_sub == exp_sub
    mark = 'PASS' if ok else 'FAIL'
    if not ok: all_ok = False
    print(f'  {mark}: [{got_intent or "none":8}][{(got_sub or "-"):4}] <- "{q}"')
print(f'\nAll pass: {all_ok}')
