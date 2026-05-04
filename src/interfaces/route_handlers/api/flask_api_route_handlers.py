from flask import request, jsonify, Response  # type: ignore
import json
import asyncio

from agent.payment_agent import PaymentAgent

agent = PaymentAgent()


def flask_api_chat_stream():
    try:
        data = request.get_json() or {}
        message = str(data.get('message', '')).strip()

        if not message:
            return jsonify({'error': 'Message cannot be empty'}), 400

        response_text = asyncio.run(agent.process(message))

        def generate():
            yield ': connected\n\n'
            done_data = {
                'response': response_text,
                'awaiting_next': None
            }
            yield f"event: done\ndata: {json.dumps(done_data)}\n\n"

        return Response(generate(), mimetype='text/event-stream', headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
