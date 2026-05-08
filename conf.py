import os

akey = 'yandexlyceum_secret_key'
avex = {'jpg', 'jpeg', 'png', 'webp', 'gif'}
avdir = os.path.join('data', 'avatars')
ctok = 60 * 60 * 24 * 14
pubapi = os.environ.get('PUBLIC_API_BASE', 'https://cryptohomyak.team/api').rstrip('/')
