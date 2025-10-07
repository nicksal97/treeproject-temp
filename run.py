"""
Application entry point
"""
import os
from app import create_app

# Get environment from env variable, default to development
config_name = os.environ.get('FLASK_ENV', 'development')

app = create_app(config_name)

if __name__ == '__main__':
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5003))
    debug = config_name == 'development'
    
    app.run(host=host, port=port, debug=debug)

