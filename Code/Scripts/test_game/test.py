# Discrete event (one decision fires once)
webview.evaluate_js("window.eegLeft()")
webview.evaluate_js("window.eegRight()")

# Continuous probability stream (best for tug of war)
webview.evaluate_js(f"window.eegSignal({left_prob}, {right_prob})")