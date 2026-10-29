"""Private feedback leads and their retryable owner-email delivery."""
from db.pool import connection


async def claim(limit: int = 10) -> list[dict]:
    async with connection() as cx:
        return await (await cx.execute("""
            with due as (
              select id from public.product_feedback
              where delivery_status='pending' and next_attempt_at<=now()
                and (claimed_until is null or claimed_until<=now())
              order by created_at,id limit %s for update skip locked
            )
            update public.product_feedback f set claimed_until=now()+interval '5 minutes',claim_token=gen_random_uuid()
            from due where f.id=due.id returning f.*
        """, (limit,))).fetchall()


async def mark_sent(feedback_id, token, provider_id: str | None) -> None:
    async with connection() as cx:
        await cx.execute("""update public.product_feedback
            set delivery_status='sent',sent_at=now(),provider_id=%s,error=null,
                attempts=attempts+1,claimed_until=null,claim_token=null
            where id=%s and claim_token=%s and delivery_status='pending'""", (provider_id,feedback_id,token))


async def mark_retry(feedback_id, token, error: str, *, retry: bool = True) -> None:
    async with connection() as cx:
        await cx.execute("""update public.product_feedback
            set delivery_status=case when not %s or attempts+1>=5 then 'failed' else 'pending' end,
                error=%s,attempts=attempts+1,next_attempt_at=now()+make_interval(secs=>60*power(2,least(attempts,6))::int),
                claimed_until=null,claim_token=null
            where id=%s and claim_token=%s and delivery_status='pending'""", (retry,error[:300],feedback_id,token))
