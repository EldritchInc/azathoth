def start_ui():
    from .ui_server import app
    app.run(host='127.0.0.1', port=5000, debug=True)