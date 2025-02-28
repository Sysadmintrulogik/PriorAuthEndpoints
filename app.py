import os
from flask import Flask
from flask_cors import CORS
from flask_smorest import Api
from create_edi import edi_bp
from priorauth_workflow import wfo_bp
from create_edi_response import edi_resp_bp
from priorauth_workflow_response import wfo_resp_bp

app = Flask(__name__)

CORS(app)

app.config["PROPAGATE_EXCEPTIONS"] = True
app.config["API_TITLE"] = os.getenv("API_TITLE", "Trulogik priorAuth APIs")
app.config["API_VERSION"] = os.getenv("API_VERSION", "v1")
app.config["OPENAPI_VERSION"] = "3.0.3"
app.config["OPENAPI_URL_PREFIX"] = os.getenv("OPENAPI_URL_PREFIX", "/")

api = Api(app)

api.register_blueprint(edi_bp)
api.register_blueprint(wfo_bp)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("APP_PORT", 8000)), debug=bool(os.getenv("DEBUG", False)))
