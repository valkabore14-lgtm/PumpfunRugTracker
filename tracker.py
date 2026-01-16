from datetime import datetime, timedelta, timezone
from config import PUMPFUN_PROGRAM_ID, MAX_HOPS, DESC_TTL_HOURS, MIN_SOL_FUNDING
from notify import telegram_send

def _utcnow():
    return datetime.now(timezone.utc)

def _looks_like_pumpfun_create(tx: dict) -> bool:
    # Méthode simple : si la transaction contient le program id Pump.fun quelque part
    # + un mot "create" dans les logs.
    text = str(tx).lower()
    if PUMPFUN_PROGRAM_ID.lower() not in text:
        return False
    return ("create" in text)  # volontairement large pour débuter

def _extract_mint(tx: dict) -> str:
    # Heuristique simple : on cherche un champ "mint" si provider le donne.
    text = str(tx)
    # fallback
    return "unknown_mint"

def process_helius_event(db, payload: dict):
    txs = payload if isinstance(payload, list) else [payload]

    for tx in txs:
        signature = tx.get("signature") or tx.get("transactionSignature") or "unknown"

        # 1) Transferts SOL natifs (Helius enhanced)
        native_transfers = tx.get("nativeTransfers") or []
        for t in native_transfers:
            src = t.get("fromUserAccount")
            dst = t.get("toUserAccount")
            amount = t.get("amount")  # souvent en SOL
            if not (src and dst and amount is not None):
                continue
            if not db.is_watched(src):
                continue
            if float(amount) < MIN_SOL_FUNDING:
                continue

            src_row = db.get_wallet(src)
            hop = int(src_row["hop"]) + 1 if src_row else 1
            if hop > MAX_HOPS:
                continue

            expires_at = (_utcnow() + timedelta(hours=DESC_TTL_HOURS)).isoformat()
            db.add_descendant(src, dst, hop, expires_at)
            db.add_edge(src, dst, int(float(amount) * 1_000_000_000), signature)

        # 2) Création Pump.fun
        if db.already_seen_create(signature):
            continue

        if _looks_like_pumpfun_create(tx):
            creator = tx.get("feePayer") or "unknown_creator"
            mint = _extract_mint(tx)
            db.mark_seen_create(signature, mint, str(creator))

            chain = db.trace_to_seed(str(creator)) if creator else [str(creator)]
            chain_str = " -> ".join(chain)

            msg = (
                "🟣 Pump.fun CREATE détecté\n"
                f"Creator: {creator}\n"
                f"Mint/CA: {mint}\n"
                f"Funding chain: {chain_str}\n"
                f"Tx: https://solscan.io/tx/{signature}\n"
            )
            telegram_send(msg)
