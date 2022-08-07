import requests

req = requests.get('https://cs1-67v4.vkuservideo.net/p10/1b4b195eeb27.480.mp4')

with open('video.mp4', 'wb') as video:
    video.write(req.content)