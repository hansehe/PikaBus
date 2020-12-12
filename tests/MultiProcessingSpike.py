import asyncio
import concurrent.futures
import functools
import logging
import sys
import time


class DummyClass:
    def __init__(self, loop = None):
        self._loop = loop


SOME_GLOBAL = 0


def blocks(n, someObject = None):
    global SOME_GLOBAL
    log = logging.getLogger('blocks({})'.format(n))
    SOME_GLOBAL += 1
    log.info(f'running {SOME_GLOBAL}')
    time.sleep(0.1)
    log.info('done')
    return n ** 2


async def run_blocking_tasks(executor):
    log = logging.getLogger('run_blocking_tasks')
    log.info('starting')

    log.info('creating executor tasks')
    loop = asyncio.get_event_loop()
    dummy = DummyClass(loop=loop)
    dummy = {'test': 123, 'test2': {'lol': ''}}
    blocking_tasks = []
    for i in range(6):
        func = functools.partial(blocks, i, dummy)
        blocking_tasks.append(loop.run_in_executor(executor, func))
    log.info('waiting for executor tasks')
    completed, pending = await asyncio.wait(blocking_tasks)
    results = [t.result() for t in completed]
    log.info('results: {!r}'.format(results))

    log.info('exiting')


if __name__ == '__main__':
    # Configure logging to show the id of the process
    # where the log message originates.
    logging.basicConfig(
        level=logging.INFO,
        format='PID %(process)5s %(name)18s: %(message)s',
        stream=sys.stderr,
    )

    # Create a limited process pool.
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=3,
    )
    # executor = concurrent.futures.ProcessPoolExecutor(
    #     max_workers=3,
    # )

    event_loop = asyncio.get_event_loop()
    try:
        event_loop.run_until_complete(
            run_blocking_tasks(executor)
        )
    finally:
        event_loop.close()
