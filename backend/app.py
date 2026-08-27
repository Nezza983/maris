from flask import Flask, request, jsonify
from flask_cors import CORS
import time
import uuid

app = Flask(__name__)
CORS(app)


@app.route("/")
def home():
    return jsonify({
        "system": "MARIS",
        "message": "Maritime Intelligence & Response System",
        "status": "online"
    })


@app.route("/api/analyze", methods=["POST"])
def analyze():

    # Check whether an image was uploaded
    if "image" not in request.files:
        return jsonify({
            "success": False,
            "error": "No SAR image uploaded"
        }), 400

    image = request.files["image"]

    # Basic validation
    if image.filename == "":
        return jsonify({
            "success": False,
            "error": "No image selected"
        }), 400


    # Generate an investigation ID
    investigation_id = "MARIS-" + str(uuid.uuid4())[:8].upper()


    # ------------------------------------------------
    # MOCK ANALYSIS
    # This will later be replaced by the real modules
    # ------------------------------------------------

    result = {

        "success": True,

        "investigation_id": investigation_id,

        "status": "complete",

        "detection": {

            "oil_detected": True,

            "confidence": 0.947,

            "severity": "HIGH",

            "spill_area_km2": 72.97

        },


        "spill": {

            "latitude": 10.719613,

            "longitude": 72.932878,

            "timestamp": "2026-08-26T07:55:32Z"

        },


        "environment": {

            "wind_speed_ms": 6.4,

            "wind_direction_deg": 245,

            "current_speed_ms": 0.8,

            "current_direction_deg": 220

        },


        "drift": {

            "predicted_positions": [

                {
                    "latitude": 12.345598,

                    "longitude": 74.567795,

                    "time": "2026-08-26T09:30:00Z"
                },

                {
                    "latitude": 12.323040,

                    "longitude": 74.544937,

                    "time": "2026-08-26T10:30:00Z"
                }

            ],

            "trajectory": [

                [74.567795, 12.345598],

                [74.544937, 12.323040]

            ]

        },


        "source": {

            "latitude": 12.885778,

            "longitude": 75.103512,

            "confidence": 0.35

        },


        "risk": {

            "level": "HIGH",

            "coastal_impact_probability": 0.85

        },


        "vessels": [

            {

                "rank": 1,

                "vessel_id": "123456789",

                "vessel_name": "MV Example",

                "score": 0.91,

                "score_breakdown": {

                    "distance": 0.95,

                    "time_match": 0.92,

                    "trajectory_match": 0.87,

                    "ais_continuity": 0.81

                }

            },


            {

                "rank": 2,

                "vessel_id": "987654321",

                "vessel_name": "MV Ocean Star",

                "score": 0.73,

                "score_breakdown": {

                    "distance": 0.80,

                    "time_match": 0.70,

                    "trajectory_match": 0.75,

                    "ais_continuity": 0.65

                }

            }

        ]

    }


    return jsonify(result)


if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )