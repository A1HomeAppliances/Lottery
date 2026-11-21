import os

if "ANDROID_ARGUMENT" in os.environ:           # set by python-for-android
    from shell import ShellApp
    ShellApp().run()
else:
    # Desktop: Kivy has no embedded WebView -> preview in the browser.
    import dev_server
    dev_server.main()
