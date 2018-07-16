#!/usr/bin/python3
"""
    Send a string-to-be-printed to AMQP.
"""

import trio_click as click
import sys
import trio
import json
import trio_amqp

async def handle_return(channel, body, envelope, properties):
    print('Got a returned message with routing key: {}.\n'
          'Return code: {}\n'
          'Return message: {}\n'
          'exchange: {}'.format(envelope.routing_key, envelope.reply_code,
                                envelope.reply_text, envelope.exchange_name))


async def get_returns(chan, task_status=trio.TASK_STATUS_IGNORED):
    task_status.started()
    # DO NOT await() between these statements
    async for body, envelope, properties in chan:
        await handle_return(chan, body, envelope, properties)


async def send(args):
    async with trio_amqp.connect_amqp(host=args['host'], login=args['login'], password=args['password'], virtualhost=args['vhost']) as protocol:
        channel = await protocol.channel()
        await protocol.nursery.start(get_returns, channel)

        await channel.queue_declare(exclusive=True)

        await channel.basic_publish(
            payload=json.dumps(dict(barcode=args['barcode'], text=args['text'])).encode("utf-8"),
            exchange_name=args['exchange'],
            routing_key=args['route'],  # typo on purpose, will cause the return
            mandatory=True,
        )

        await trio.sleep(3)

@click.command()
@click.option('-h','--host', help="AMQP host to connect to", default="localhost")
@click.option('-l','--login', help="AMQP user name", default="guest")
@click.option('-p','--password', help="AMQP password", default="guest")
@click.option('-v','--vhost', help="AMQP virtual host to use", default="/")
@click.option('-x','--exchange', help="Exchange to link to", default="")
@click.option('-r','--route', help="Routing key to listen on", default="")
@click.argument("barcode", nargs=1)
@click.argument("text", nargs=-1)
async def run(**args):
    await send(args)

if __name__ == "__main__":
    run()
