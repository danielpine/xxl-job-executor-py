import logging

from excutor import xxljob

logger = logging.getLogger('default')


@xxljob(name="Job_Test")
def test_task(data):
    logger.info(f"trggering task Job_Test {data}")
    pass
