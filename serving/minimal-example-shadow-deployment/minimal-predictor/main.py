import logging
import os
from typing import Dict

from kserve import Model, ModelServer

logger = logging.getLogger(__name__)


class CustomPredictor(Model):
    def __init__(self, name: str, factor: int):
        super().__init__(name)
        self.name = name
        self.ready = True
        self.factor = factor

    def predict(
        self, payload: Dict, headers: Dict = None, response_headers: Dict = None
    ) -> Dict:
        """Takes floating point values, doubles it and return the result"""

        if "values" not in payload or not payload["values"]:
            return {"predictions": ["No values provided"]}

        results = []
        for value in payload["values"]:
            try:
                results.append(self.factor * float(value))
            except ValueError as e:
                logger.error("Unable to cast values to float %s", e)
        return {"results": results}


if __name__ == "__main__":
    model_name = os.environ.get("MODEL_NAME", "doubler")
    factor = os.environ.get("FACTOR", "2")
    factor = int(factor)
    model = CustomPredictor(model_name, factor)
    ModelServer().start([model])
