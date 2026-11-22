[app]
title = A1 Lucky Spin
package.name = a1luckyspin
package.domain = com.a1
source.dir = .
# html/css/js = the web UI shown in the WebView.
# "db" is intentionally NOT listed so your local test lottery.db is never shipped.
source.include_exts = py,png,jpg,ttf,html,css,js,svg,woff2,woff
source.exclude_dirs = bin, .buildozer, __pycache__, .git
source.exclude_patterns = *.bak, *.log, lottery.db, *.db
version = 1.0

# KivyMD / pillow / materialyoucolor / libthorvg are no longer needed: the UI is
# HTML now, Kivy only hosts the WebView.  sqlite3 is REQUIRED on Android.
requirements = python3, sqlite3, kivy==2.3.1, pyjnius, android

orientation = all
#orientation = portrait
fullscreen = 0
android.permissions = INTERNET
android.archs = arm64-v8a, armeabi-v7a

android.api = 33
android.minapi = 24
android.ndk = 25b
android.ndk_path = /home/godhome/.buildozer/android/platform/android-ndk-r25b
android.accept_sdk_license = True
android.logcat_filters = *:S python:D

p4a.branch = develop

[buildozer]
pip_index_url = https://pypi.org/simple
log_level = 2
warn_on_root = 1
