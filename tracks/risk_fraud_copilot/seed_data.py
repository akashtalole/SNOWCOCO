"""Generates synthetic customers, accounts, and transactions for the demo.

All data is fabricated. Fraud/risk patterns are deliberately embedded so the
signal-detection engine (engine/signals.py) has something to find:
  - ACC-1001 : structuring / smurfing (sub-$10k cash deposits)
  - ACC-1002 : rapid layering (large wire in, fanned out fast)
  - ACC-1003 : dormant account reactivation
  - ACC-1004 : repeated high-risk jurisdiction wires
  - ACC-1005 : ATM card-testing / mule pattern

  - ACC-1006 : round-dollar international wire pattern
  - ACC-1007 : new-account high-value activity
  - ACC-1008 : transaction velocity spike

  UPI Fraud & Mule Account Network module (India, see policies/upi_fraud_mule_detection.md):
  - ACC-1009 : UPI mule hub (fan-in from 6 senders, fan-out to 2 ring members + cash-out)
  - ACC-1010 : UPI mule ring member A (independently fans in/out; linked to ACC-1009)
  - ACC-1011 : UPI mule ring member B (independently fans in/out; linked to ACC-1009)
  - ACC-1012 : new-beneficiary high-value UPI payment (OTP/social-engineering victim pattern)
  - ACC-1013 : dormant VPA reactivated by a burst of unrelated credits

Run (from repo root): python3 -m tracks.risk_fraud_copilot.seed_data
"""
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

NOW = datetime(2026, 9, 21, 12, 0, 0)
COUNTRIES_NORMAL = ["US", "UK", "DE", "SG", "CA", "AU", "JP", "IN"]
COUNTRIES_HIGH_RISK = ["ZX", "QW"]  # see app/policies/sanctions_screening.md

FIRST_NAMES = ["Amara", "Liam", "Priya", "Noah", "Sofia", "Kenji", "Elena", "Omar",
               "Grace", "Lucas", "Nadia", "Hugo", "Mei", "Ivan", "Zara", "Tom",
               "Ravi", "Chloe", "Yusuf", "Anna"]
LAST_NAMES = ["Okafor", "Meyer", "Sharma", "Kowalski", "Nakamura", "Rossi", "Novak",
              "Silva", "Andersen", "Costa", "Khan", "Dubois", "Chen", "Petrov",
              "Larsen", "Flores"]
BUSINESS_NAMES = ["Alden Freight Co", "Brightline Retail", "Cobalt Logistics",
                   "Delta Wholesale", "Everview Consulting", "Fenwick Traders",
                   "Golden Gate Imports", "Harbor Supply Corp"]

INDIAN_FIRST_NAMES = ["Ravi", "Sunita", "Deepak", "Meera", "Arjun", "Priya", "Kiran", "Anjali",
                       "Vikram", "Neha", "Suresh", "Divya", "Rohit", "Pooja", "Manoj", "Kavita"]
INDIAN_LAST_NAMES = ["Kumar", "Sharma", "Iyer", "Reddy", "Nair", "Patel", "Gupta", "Verma",
                      "Rao", "Menon", "Joshi", "Desai"]
UPI_HANDLES = ["oksbi", "ybl", "paytm", "okhdfcbank", "okicici", "okaxis"]
UPI_REGULAR_PAYEES = ["landlord.rent@oksbi", "mom.and.dad@ybl", "electricity.board@paytm",
                       "friend.raj@oksbi", "grocery.kirana@ybl", "mobile.recharge@paytm"]

CUSTOMERS = []
ACCOUNTS = []
TRANSACTIONS = []

txn_counter = 1


def new_txn_id():
    global txn_counter
    tid = f"TXN-{txn_counter:06d}"
    txn_counter += 1
    return tid


def make_customer(idx, ctype, country, risk="Low", indian=False):
    cid = f"CUST-{1000 + idx}"
    if ctype == "individual":
        if indian:
            name = f"{random.choice(INDIAN_FIRST_NAMES)} {random.choice(INDIAN_LAST_NAMES)}"
        else:
            name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        occupation = random.choice(["Software Engineer", "Teacher", "Nurse", "Consultant",
                                     "Retail Manager", "Accountant", "Electrician"])
    else:
        name = random.choice(BUSINESS_NAMES) + f" #{idx}"
        occupation = random.choice(["Import/Export", "Retail", "Logistics", "Consulting"])
    onboarding = NOW - timedelta(days=random.randint(200, 1800))
    CUSTOMERS.append({
        "customer_id": cid, "name": name, "type": ctype,
        "risk_rating": risk, "country": country,
        "occupation_or_industry": occupation,
        "onboarding_date": onboarding.date().isoformat(),
    })
    return cid


def make_account(customer_id, acct_id_override=None, opened_days_ago=400, acct_type="checking",
                  vpa=""):
    aid = acct_id_override or f"ACC-{2000 + len(ACCOUNTS)}"
    ACCOUNTS.append({
        "account_id": aid, "customer_id": customer_id, "account_type": acct_type,
        "opened_date": (NOW - timedelta(days=opened_days_ago)).date().isoformat(),
        "status": "active", "currency": "USD", "vpa": vpa,
    })
    return aid


def add_txn(account_id, customer_id, ts, amount, ttype, counterparty="", cp_country="US",
            channel="online", location="", description="", currency="USD"):
    TRANSACTIONS.append({
        "txn_id": new_txn_id(), "account_id": account_id, "customer_id": customer_id,
        "timestamp": ts.isoformat(), "amount": round(amount, 2), "currency": currency,
        "type": ttype, "counterparty_name": counterparty, "counterparty_country": cp_country,
        "channel": channel, "location": location, "description": description,
    })


def gen_normal_history(account_id, customer_id, days=220, activity="normal", vpa="",
                        end_buffer_days=0):
    """Background noise transactions so signals aren't the only data present.

    end_buffer_days stops noise generation that many days before NOW, so it can't
    coincidentally land inside a hand-crafted pattern's own detection window.
    """
    start = NOW - timedelta(days=days)
    end = NOW - timedelta(days=end_buffer_days)
    t = start
    while t < end:
        t += timedelta(days=random.randint(2, 6))
        if t >= end:
            break
        choices = ["pos_purchase", "ach_in", "ach_out", "atm_withdrawal", "wire_in"]
        weights = [50, 15, 15, 15, 5]
        if vpa:
            choices += ["upi_out", "upi_in"]
            weights += [25, 10]
        kind = random.choices(choices, weights=weights)[0]
        if kind == "upi_out":
            add_txn(account_id, customer_id, t, random.uniform(100, 2500), kind,
                    counterparty=random.choice(UPI_REGULAR_PAYEES), cp_country="IN",
                    channel="upi", description="UPI payment", currency="INR")
        elif kind == "upi_in":
            add_txn(account_id, customer_id, t, random.uniform(200, 3000), kind,
                    counterparty=f"contact{random.randint(1,9)}@{random.choice(UPI_HANDLES)}",
                    cp_country="IN", channel="upi", description="UPI receipt", currency="INR")
        elif kind == "pos_purchase":
            add_txn(account_id, customer_id, t, random.uniform(8, 220), kind,
                    counterparty=random.choice(["Grocer Mart", "Fuel Stop", "Cafe Nero",
                                                 "Online Retailer", "Utility Co"]),
                    channel="pos", description="Everyday purchase")
        elif kind == "ach_in":
            add_txn(account_id, customer_id, t, random.uniform(800, 4500), kind,
                    counterparty="Payroll Inc", channel="ach", description="Payroll deposit")
        elif kind == "ach_out":
            add_txn(account_id, customer_id, t, random.uniform(50, 900), kind,
                    counterparty=random.choice(["Landlord LLC", "Credit Card Co", "Insurer Co"]),
                    channel="ach", description="Bill payment")
        elif kind == "atm_withdrawal":
            add_txn(account_id, customer_id, t, random.choice([40, 60, 100, 140, 200]), kind,
                    channel="atm", location=f"Branch {random.randint(1,12)}",
                    description="ATM withdrawal")
        elif kind == "wire_in":
            add_txn(account_id, customer_id, t, random.uniform(1000, 6000), kind,
                    counterparty="External Party", cp_country=random.choice(COUNTRIES_NORMAL),
                    channel="wire", description="Incoming wire")


def build():
    idx = 0

    # --- Normal population (noise) ---
    for i in range(20):
        idx += 1
        ctype = "individual" if i % 4 != 0 else "business"
        # Every 3rd noise account gets an Indian identity + UPI activity, so the UPI rail
        # has realistic everyday traffic and isn't populated only by fraud demo accounts.
        indian = (i % 3 == 0)
        country = "IN" if indian else random.choice(COUNTRIES_NORMAL)
        cid = make_customer(idx, ctype, country, indian=indian)
        vpa = f"{CUSTOMERS[-1]['name'].lower().replace(' ', '.')}{random.randint(10,99)}@" \
              f"{random.choice(UPI_HANDLES)}" if indian else ""
        aid = make_account(cid, opened_days_ago=random.randint(200, 1500), vpa=vpa)
        gen_normal_history(aid, cid, vpa=vpa)

    # --- Pattern 1: Structuring (ACC-1001) ---
    idx += 1
    cust = make_customer(idx, "individual", "US", risk="Medium")
    acc = make_account(cust, acct_id_override="ACC-1001", opened_days_ago=500)
    gen_normal_history(acc, cust, days=150)
    base = NOW - timedelta(days=6)
    for i, amt in enumerate([9200, 8600, 9800, 8950]):
        ts = base + timedelta(days=i * 1.4)
        add_txn(acc, cust, ts, amt, "cash_deposit", counterparty="Teller Branch 4",
                channel="branch", description="Cash deposit")

    # --- Pattern 2: Rapid layering (ACC-1002) ---
    idx += 1
    cust = make_customer(idx, "business", "US", risk="Medium")
    acc = make_account(cust, acct_id_override="ACC-1002", opened_days_ago=300)
    gen_normal_history(acc, cust, days=150)
    t0 = NOW - timedelta(hours=40)
    add_txn(acc, cust, t0, 26000, "wire_in", counterparty="Overseas Buyer Ltd",
            cp_country="SG", channel="wire", description="Trade payment received")
    fanout = [
        (8000, "Consultant A", "UK"), (7200, "Consultant B", "DE"),
        (6800, "Consultant C", "CA"), (3200, "Consultant D", "AU"),
    ]
    for i, (amt, cp, country) in enumerate(fanout):
        ts = t0 + timedelta(hours=6 + i * 8)
        add_txn(acc, cust, ts, amt, "wire_out", counterparty=cp, cp_country=country,
                channel="wire", description="Outgoing wire")

    # --- Pattern 3: Dormant reactivation (ACC-1003) ---
    idx += 1
    cust = make_customer(idx, "individual", "UK", risk="Low")
    acc = make_account(cust, acct_id_override="ACC-1003", opened_days_ago=900)
    dormant_end = NOW - timedelta(days=210)
    gen_normal_history(acc, cust, days=1, activity="dormant")  # near-empty
    # backdate a few old transactions well before the dormancy window
    old_t = NOW - timedelta(days=260)
    for i in range(3):
        add_txn(acc, cust, old_t + timedelta(days=i * 3), random.uniform(100, 500),
                "pos_purchase", counterparty="Old Purchase", channel="pos")
    reactivate_t = NOW - timedelta(days=2)
    add_txn(acc, cust, reactivate_t, 7500, "wire_out", counterparty="Unknown Payee",
            cp_country="CA", channel="wire", description="Large outgoing wire after dormancy")

    # --- Pattern 4: High-risk jurisdiction wires (ACC-1004) ---
    idx += 1
    cust = make_customer(idx, "business", "US", risk="Medium")
    acc = make_account(cust, acct_id_override="ACC-1004", opened_days_ago=600)
    gen_normal_history(acc, cust, days=150)
    base = NOW - timedelta(days=18)
    for i in range(3):
        ts = base + timedelta(days=i * 7)
        add_txn(acc, cust, ts, random.uniform(4000, 9000), "wire_out",
                counterparty=f"Vendor {i+1}", cp_country=random.choice(COUNTRIES_HIGH_RISK),
                channel="wire", description="International wire")

    # --- Pattern 5: ATM card-testing / mule (ACC-1005) ---
    idx += 1
    cust = make_customer(idx, "individual", "US", risk="Low")
    acc = make_account(cust, acct_id_override="ACC-1005", opened_days_ago=250)
    gen_normal_history(acc, cust, days=150)
    base = NOW - timedelta(days=3, hours=5)
    for i in range(6):
        ts = base + timedelta(minutes=i * 40)
        add_txn(acc, cust, ts, 200, "atm_withdrawal", channel="atm",
                location=f"Branch {random.randint(20, 40)}", description="ATM withdrawal")

    # --- Pattern 6: Round-dollar international wire pattern (ACC-1006) ---
    idx += 1
    cust = make_customer(idx, "business", "US", risk="Medium")
    acc = make_account(cust, acct_id_override="ACC-1006", opened_days_ago=400)
    gen_normal_history(acc, cust, days=150)
    base = NOW - timedelta(days=10)
    for i, (amt, country) in enumerate([(5000, "UK"), (2500, "DE"), (7500, "SG")]):
        ts = base + timedelta(days=i * 3)
        add_txn(acc, cust, ts, amt, "wire_out", counterparty=f"Overseas Vendor {i+1}",
                cp_country=country, channel="wire", description="International wire")

    # --- Pattern 7: New account high-value activity (ACC-1007) ---
    idx += 1
    cust = make_customer(idx, "individual", "US", risk="Medium")
    acc = make_account(cust, acct_id_override="ACC-1007", opened_days_ago=20)
    gen_normal_history(acc, cust, days=15)
    add_txn(acc, cust, NOW - timedelta(days=5), 15000, "wire_in", counterparty="Large Depositor",
            cp_country="US", channel="wire",
            description="Large inbound wire shortly after account opening")

    # --- Pattern 8: Transaction velocity spike (ACC-1008) ---
    idx += 1
    cust = make_customer(idx, "individual", "US", risk="Low")
    acc = make_account(cust, acct_id_override="ACC-1008", opened_days_ago=300)
    gen_normal_history(acc, cust, days=150)
    base = NOW - timedelta(days=1, hours=10)
    for i in range(8):
        ts = base + timedelta(minutes=i * 30)
        add_txn(acc, cust, ts, random.uniform(20, 150), "pos_purchase",
                counterparty="Retail Store", channel="pos", description="Rapid purchase spike")

    # --- Pattern 9-11: UPI mule hub + ring (ACC-1009, ACC-1010, ACC-1011) ---
    # A 3-hub star-shaped mule ring: ACC-1009 is the root hub, fanning out to ring members
    # ACC-1010 and ACC-1011, each of which independently also exhibits the fan-in/fan-out
    # "mule hub" signature and further disperses to external cash-out VPAs. Detecting each
    # account individually finds 3 separate Mule Hub signals; the graph-based ring detector
    # (UPI-MULE-3) is what recognizes they're one connected laundering network.
    t0 = NOW - timedelta(days=3, hours=10)

    idx += 1
    cust_hub = make_customer(idx, "individual", "IN", risk="Medium", indian=True)
    acc_hub = make_account(cust_hub, acct_id_override="ACC-1009", opened_days_ago=10,
                            vpa="ravi.k.9821@oksbi")
    gen_normal_history(acc_hub, cust_hub, days=8)

    idx += 1
    cust_a = make_customer(idx, "individual", "IN", risk="Low", indian=True)
    acc_a = make_account(cust_a, acct_id_override="ACC-1010", opened_days_ago=500,
                          vpa="sunita.trades@ybl")
    gen_normal_history(acc_a, cust_a, days=150, vpa="sunita.trades@ybl", end_buffer_days=3)

    idx += 1
    cust_b = make_customer(idx, "individual", "IN", risk="Low", indian=True)
    acc_b = make_account(cust_b, acct_id_override="ACC-1011", opened_days_ago=600,
                          vpa="deepak.retail@paytm")
    gen_normal_history(acc_b, cust_b, days=150, vpa="deepak.retail@paytm", end_buffer_days=3)

    # Hub inflow: 6 distinct external "source" VPAs within a 30h window
    hub_sources = [
        ("unknown1@ybl", 45000), ("unknown2@paytm", 62000), ("unknown3@oksbi", 38000),
        ("unknown4@ybl", 71000), ("unknown5@paytm", 55000), ("unknown6@oksbi", 40000),
    ]
    for i, (vpa, amt) in enumerate(hub_sources):
        ts = t0 + timedelta(hours=i * 6)
        add_txn(acc_hub, cust_hub, ts, amt, "upi_in", counterparty=vpa, cp_country="IN",
                channel="upi", description="UPI receipt", currency="INR")
    hub_last_inflow = t0 + timedelta(hours=5 * 6)

    # Hub fan-out: to ring member A, ring member B, and one external cash-out, within 24h
    hub_fanout = [
        (acc_a, "sunita.trades@ybl", 130000, 2),
        (acc_b, "deepak.retail@paytm", 90000, 4),
        (None, "cashout.point1@oksbi", 60000, 6),
    ]
    for target_acc, vpa, amt, hours_after in hub_fanout:
        ts = hub_last_inflow + timedelta(hours=hours_after)
        add_txn(acc_hub, cust_hub, ts, amt, "upi_out", counterparty=vpa, cp_country="IN",
                channel="upi", description="UPI payment", currency="INR")
        if target_acc:
            add_txn(target_acc, cust_a if target_acc == acc_a else cust_b, ts, amt, "upi_in",
                    counterparty="ravi.k.9821@oksbi", cp_country="IN", channel="upi",
                    description="UPI receipt", currency="INR")

    # Ring member A: hub payment (already added above) + 4 more distinct small senders
    a_hub_in_ts = hub_last_inflow + timedelta(hours=2)
    a_more_sources = [
        ("buyer1@ybl", 30000), ("buyer2@paytm", 25000), ("buyer3@oksbi", 28000), ("buyer4@ybl", 22000),
    ]
    for i, (vpa, amt) in enumerate(a_more_sources):
        ts = a_hub_in_ts + timedelta(hours=1 + i)
        add_txn(acc_a, cust_a, ts, amt, "upi_in", counterparty=vpa, cp_country="IN",
                channel="upi", description="UPI receipt", currency="INR")
    a_last_inflow = a_hub_in_ts + timedelta(hours=1 + len(a_more_sources) - 1)
    a_fanout = [("cash2a@oksbi", 80000), ("cash2b@ybl", 70000), ("cash2c@paytm", 60000)]
    for i, (vpa, amt) in enumerate(a_fanout):
        ts = a_last_inflow + timedelta(hours=1 + i)
        add_txn(acc_a, cust_a, ts, amt, "upi_out", counterparty=vpa, cp_country="IN",
                channel="upi", description="UPI payment", currency="INR")

    # Ring member B: hub payment (already added above) + 4 more distinct small senders
    b_hub_in_ts = hub_last_inflow + timedelta(hours=4)
    b_more_sources = [
        ("cust1@oksbi", 26000), ("cust2@ybl", 31000), ("cust3@paytm", 24000), ("cust4@oksbi", 29000),
    ]
    for i, (vpa, amt) in enumerate(b_more_sources):
        ts = b_hub_in_ts + timedelta(hours=1 + i * 0.5)
        add_txn(acc_b, cust_b, ts, amt, "upi_in", counterparty=vpa, cp_country="IN",
                channel="upi", description="UPI receipt", currency="INR")
    b_last_inflow = b_hub_in_ts + timedelta(hours=1 + (len(b_more_sources) - 1) * 0.5)
    b_fanout = [("cash3a@ybl", 60000), ("cash3b@oksbi", 55000), ("cash3c@paytm", 50000)]
    for i, (vpa, amt) in enumerate(b_fanout):
        ts = b_last_inflow + timedelta(hours=1.5 + i)
        add_txn(acc_b, cust_b, ts, amt, "upi_out", counterparty=vpa, cp_country="IN",
                channel="upi", description="UPI payment", currency="INR")

    # --- Pattern 12: New-beneficiary high-value UPI payment (ACC-1012) ---
    idx += 1
    cust_v = make_customer(idx, "individual", "IN", risk="Low", indian=True)
    acc_v = make_account(cust_v, acct_id_override="ACC-1012", opened_days_ago=700,
                          vpa="meera.iyer@oksbi")
    gen_normal_history(acc_v, cust_v, days=150, vpa="meera.iyer@oksbi")
    victim_base = NOW - timedelta(days=150)
    for i in range(18):
        ts = victim_base + timedelta(days=i * 8)
        add_txn(acc_v, cust_v, ts, random.uniform(300, 2500), "upi_out",
                counterparty=random.choice(UPI_REGULAR_PAYEES), cp_country="IN", channel="upi",
                description="UPI payment", currency="INR")
    add_txn(acc_v, cust_v, NOW - timedelta(days=2), 185000, "upi_out",
            counterparty="unknown.investment@paytm", cp_country="IN", channel="upi",
            description="UPI payment", currency="INR")

    # --- Pattern 13: Dormant VPA reactivation burst (ACC-1013) ---
    idx += 1
    cust_d = make_customer(idx, "individual", "IN", risk="Low", indian=True)
    acc_d = make_account(cust_d, acct_id_override="ACC-1013", opened_days_ago=800,
                          vpa="arjun.old@oksbi")
    old_upi_t = NOW - timedelta(days=110)
    for i in range(3):
        add_txn(acc_d, cust_d, old_upi_t + timedelta(days=i * 4), random.uniform(200, 1200),
                "upi_out", counterparty=random.choice(UPI_REGULAR_PAYEES), cp_country="IN",
                channel="upi", description="UPI payment", currency="INR")
    burst_t = NOW - timedelta(hours=18)
    burst_sources = [("relative1@ybl", 15000), ("relative2@paytm", 18000),
                      ("stranger1@oksbi", 22000), ("stranger2@ybl", 19000)]
    for i, (vpa, amt) in enumerate(burst_sources):
        add_txn(acc_d, cust_d, burst_t + timedelta(hours=i * 3), amt, "upi_in",
                counterparty=vpa, cp_country="IN", channel="upi", description="UPI receipt",
                currency="INR")

    # --- ID collision check ---
    account_ids = [a["account_id"] for a in ACCOUNTS]
    customer_ids = [c["customer_id"] for c in CUSTOMERS]
    dup_accounts = {aid for aid in account_ids if account_ids.count(aid) > 1}
    dup_customers = {cid for cid in customer_ids if customer_ids.count(cid) > 1}
    assert not dup_accounts, f"Duplicate account_id(s) detected in seed data: {dup_accounts}"
    assert not dup_customers, f"Duplicate customer_id(s) detected in seed data: {dup_customers}"
    assert len(account_ids) == len(set(account_ids))
    assert len(customer_ids) == len(set(customer_ids))

    # --- write CSVs ---
    _write_csv("customers.csv", CUSTOMERS,
               ["customer_id", "name", "type", "risk_rating", "country",
                "occupation_or_industry", "onboarding_date"])
    _write_csv("accounts.csv", ACCOUNTS,
               ["account_id", "customer_id", "account_type", "opened_date", "status", "currency",
                "vpa"])
    TRANSACTIONS.sort(key=lambda r: r["timestamp"])
    _write_csv("transactions.csv", TRANSACTIONS,
               ["txn_id", "account_id", "customer_id", "timestamp", "amount", "currency",
                "type", "counterparty_name", "counterparty_country", "channel", "location",
                "description"])

    print(f"Wrote {len(CUSTOMERS)} customers, {len(ACCOUNTS)} accounts, "
          f"{len(TRANSACTIONS)} transactions to {DATA_DIR}")


def _write_csv(name, rows, fieldnames):
    path = DATA_DIR / name
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    build()
