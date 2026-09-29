import argparse
import base64
import calendar
import io
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Dict, Union

import kserve
from kserve import InferRequest, InferResponse, Model, ModelServer, model_server
from kserve.model import ModelInferRequest

from PredictionDBHandler import PredictionDBHandler

logging.basicConfig(level=kserve.constants.KSERVE_LOGLEVEL)

REQUEST_ID = "x-request-id"

logger = logging.getLogger(__name__)


class PersistTransformer(Model):
    def __init__(
        self,
        name: str,
        predictor_host: str,
        db_url: str,
    ):
        # ModelServer() builds the predictor config from --predictor_host and
        # forwards predict() calls there; the host is kept for the DB rows.
        super().__init__(name)

        if not predictor_host:
            raise ValueError("Predictor host is not defined.")
        self.predict_url = predictor_host
        self.postges_db_handler = PredictionDBHandler(db_url)
        logger.debug("Predictor host url: %s", self.predict_url)
        self.ready = True

    async def preprocess(self, payload: Dict, headers: Dict[str, str] = None) -> Dict:

        logger.debug("Request headers: %s", headers)

        if REQUEST_ID not in headers:
            logger.error(
                "Request: Header %s not found! Continue without storeing...", REQUEST_ID
            )
        else:
            self.postges_db_handler.queue_request(
                headers[REQUEST_ID],
                datetime.now(timezone.utc),
                self.predict_url,
                json.dumps(payload),
            )
        return payload

    async def predict(
        self,
        payload: Union[Dict, InferRequest, ModelInferRequest],
        headers: Dict[str, str] = None,
        response_headers: Dict[str, str] = None,
    ):
        logger.info("Header: %s", headers)
        return await super().predict(payload, headers, response_headers)

    async def postprocess(
        self,
        result: Union[Dict, InferResponse],
        headers: Dict[str, str] = None,
    ):
        logger.debug("Result: %s", result)
        if REQUEST_ID not in headers:
            logger.error(
                "Response: Header %s not found! Continue without storeing...",
                REQUEST_ID,
            )
        else:
            if isinstance(result, InferResponse):
                result = result.to_dict()

            self.postges_db_handler.queue_response(
                headers[REQUEST_ID], json.dumps(result)
            )
        return result


parser = argparse.ArgumentParser(parents=[model_server.parser])
args, _ = parser.parse_known_args()

if __name__ == "__main__":
    db_uri = os.getenv("POSTGRES_URI")
    logger.debug("Postgres URI: %s", db_uri)
    if db_uri is None:
        raise ValueError("Postgres DB uri is not defined.")

    transformer = PersistTransformer(
        args.model_name, predictor_host=args.predictor_host, db_url=db_uri
    )

    ModelServer().start(models=[transformer])
