export default {
    async queue(batch, env) {
        for (const message of batch.messages) {
            const eventData = message.body;

            const webhookPayload = {
                account_id: eventData.account,
                object_key: eventData.object.key,
                action: eventData.action,
                bucket: eventData.bucket,
                size: eventData.object.size,
                etag: eventData.object.eTag,
                event_time: eventData.eventTime
            };

            try {
                const response = await fetch(env.WEBHOOK_URL, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Webhook-Secret": env.WEBHOOK_SECRET,
                    },
                    body: JSON.stringify(webhookPayload),
                });

                if (response.ok) {
                    message.ack();
                } else {
                    console.error(`Webhook failed with status ${response.status}`);
                    message.retry();
                }
            } catch (error) {
                console.error('Webhook error:', error);
                message.retry();
            }
        }
    },
};