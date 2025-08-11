import csv
from tempfile import mktemp

from django.conf import settings
from django.contrib.auth.models import User

from judge.models import Profile, Language, Organization


fields = ['username', 'password', 'name', 'email', 'organizations']
descriptions = ['my_username(edit old one if exist)',
                 '123456 (must have)',
                 'Nguyen Van A (can be empty)',
                 'test@gmail.com (can be empty)',
                 'org1&org2&org3&... (can be empty - org slug in URL)']

def csv_to_dict(csv_file):
    rows = csv.reader(csv_file.read().decode().split('\n'))
    header = next(rows)
    header = [i.lower() for i in header]

    if 'username' not in header:
        return []

    res = []

    for row in rows:
        if len(row) != len(header):
            continue
        cur_dict = {i: '' for i in fields}
        for i in range(len(header)):
            if header[i] not in fields:
                continue
            cur_dict[header[i]] = row[i]
        if cur_dict['username']:
            res.append(cur_dict)
    return res

    
# return result log
def import_users(users):
    log = ''
    for i, row in enumerate(users):
        cur_log = str(i + 1) + '. '

        username = row['username']
        cur_log += username + ': '

        pwd = row['password']
        
        user, created = User.objects.get_or_create(username=username, defaults={
            'is_active': True,
        })

        profile, _ = Profile.objects.get_or_create(user=user, defaults={
            'language': Language.get_python3(),
            'timezone': settings.DEFAULT_USER_TIME_ZONE,
        })

        if created:
            cur_log += 'Create new - '
        else:
            cur_log += 'Edit - '

        if pwd:
            user.set_password(pwd)
        elif created:
            user.set_password('gBenqN7Xvkwjn1t')
            cur_log += 'Missing password, set password = gBenqN7Xvkwjn1t - '

        if 'name' in row.keys() and row['name']:
            user.first_name = row['name']

        if row['organizations']:
            orgs = row['organizations'].split('&')
            added_orgs = []
            for o in orgs:
                try:
                    org = Organization.objects.get(slug=o)
                    profile.organizations.add(org)
                    added_orgs.append(org.name)
                except Organization.DoesNotExist:
                    continue
            if added_orgs:
                cur_log += 'Added to ' + ', '.join(added_orgs) + ' - '

        if row['email']:
            user.email = row['email']
            
        user.save()
        profile.save()
        cur_log += 'Saved\n'
        log += cur_log
    log += 'FINISH'

    return log