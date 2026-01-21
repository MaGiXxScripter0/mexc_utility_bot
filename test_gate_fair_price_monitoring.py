#!/usr/bin/env python3
"""
Test script for Gate.io Fair Price Alert Service with 1% spread threshold.
This script tests the spread calculation logic without complex imports.
"""

import asyncio
from typing import Dict, List, Any


def calculate_spread(last_price: float, fair_price: float) -> float:
    """Calculate spread percentage."""
    if fair_price <= 0 or last_price <= 0:
        return 0.0
    return ((last_price - fair_price) / fair_price) * 100


def should_alert(last_price: float, fair_price: float, threshold: float = 1.0) -> bool:
    """Check if should alert based on spread threshold."""
    spread_pct = calculate_spread(last_price, fair_price)
    return abs(spread_pct) >= threshold


def test_spread_calculations():
    """Test spread calculation logic."""
    print("🧪 Testing spread calculations with 1% threshold:")
    print("=" * 60)

    test_cases = [
        # (last_price, fair_price, expected_spread, should_alert)
        (50000, 49750, 0.5, False),    # 0.5% spread - below threshold
        (3000, 2945, 1.9, True),      # 1.9% spread - above threshold
        (0.5, 0.49, 2.0, True),       # 2.0% spread - above threshold
        (100, 99.5, 0.5, False),      # 0.5% spread - below threshold
        (100, 98.5, 1.5, True),       # 1.5% spread - above threshold
        (10, 9.95, 0.5, False),       # 0.5% spread - below threshold
        (10, 9.85, 1.5, True),        # 1.5% spread - above threshold
    ]

    all_passed = True

    for i, (last, fair, expected_spread, expected_alert) in enumerate(test_cases, 1):
        actual_spread = calculate_spread(last, fair)
        actual_alert = should_alert(last, fair, 1.0)

        spread_ok = abs(actual_spread - expected_spread) < 0.01
        alert_ok = actual_alert == expected_alert

        status = "✅" if (spread_ok and alert_ok) else "❌"
        print(f"Test {i:2d}: Expected {expected_spread:4.1f}% | {expected_alert!s:<5} | "
              f"Actual {actual_spread:4.1f}% | {actual_alert!s:<5} | {status}")

        if not (spread_ok and alert_ok):
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("✅ All spread calculation tests PASSED")
    else:
        print("❌ Some spread calculation tests FAILED")

    return all_passed


def simulate_gate_websocket_data():
    """Simulate Gate.io WebSocket ticker data."""
    print("\n📡 Simulating Gate.io WebSocket ticker data:")
    print("=" * 60)

    # Test ticker data similar to what Gate.io sends
    ticker_data = [
        {
            "contract": "BTC_USDT",
            "last": "50000",
            "mark_price": "49750",  # 0.5% spread
            "volume_24h": "1000"
        },
        {
            "contract": "ETH_USDT",
            "last": "3000",
            "mark_price": "2945",  # 1.9% spread
            "volume_24h": "5000"
        },
        {
            "contract": "ADA_USDT",
            "last": "0.5",
            "mark_price": "0.49",  # 2.0% spread
            "volume_24h": "1000000"
        },
        {
            "contract": "SOL_USDT",
            "last": "100",
            "mark_price": "99.5",  # 0.5% spread
            "volume_24h": "50000"
        },
        {
            "contract": "DOT_USDT",
            "last": "10",
            "mark_price": "9.85",  # 1.5% spread
            "volume_24h": "100000"
        }
    ]

    alerts_sent = 0
    alert_contracts = []

    for ticker in ticker_data:
        contract = ticker["contract"]
        last_price = float(ticker["last"])
        mark_price = float(ticker["mark_price"])

        spread = calculate_spread(last_price, mark_price)
        should_send_alert = should_alert(last_price, mark_price, 1.0)

        if should_send_alert:
            alerts_sent += 1
            alert_contracts.append(contract)
            print(f"🚨 ALERT for {contract}: {spread:.1f}% spread")
        else:
            print(f"🔕 No alert for {contract}: {spread:.1f}% spread (below 1% threshold)")

    print("=" * 60)
    print(f"📊 Total alerts that would be sent: {alerts_sent}")
    print(f"Alert contracts: {alert_contracts}")
    print("Expected: 3 alerts (ETH_USDT 1.9%, ADA_USDT 2.0%, DOT_USDT 1.5%)")

    expected_alerts = 3
    return alerts_sent == expected_alerts


def test_different_thresholds():
    """Test different spread thresholds."""
    print("\n🎛️  Testing different spread thresholds:")
    print("=" * 60)

    test_price_pair = (100, 98.5)  # 1.5% spread
    last_price, fair_price = test_price_pair

    thresholds = [0.5, 1.0, 2.0, 5.0]

    for threshold in thresholds:
        spread = calculate_spread(last_price, fair_price)
        would_alert = should_alert(last_price, fair_price, threshold)

        status = "🚨 ALERT" if would_alert else "🔕 No alert"
        print(f"Threshold {threshold:3.1f}%: Spread {spread:4.1f}% → {status}")
    print("=" * 60)


async def main():
    """Main test function."""
    print("🧪 Gate.io Fair Price Alert Service Test")
    print("Testing 1% spread threshold logic")
    print("=" * 80)

    # Test spread calculations
    calc_test_passed = test_spread_calculations()

    # Test simulated WebSocket data
    ws_test_passed = simulate_gate_websocket_data()

    # Test different thresholds
    test_different_thresholds()

    # Overall result
    print("\n🎯 Final Test Results:")
    print("=" * 80)

    if calc_test_passed and ws_test_passed:
        print("✅ ALL TESTS PASSED")
        print("🎉 Gate.io fair price monitoring logic works correctly with 1% threshold!")
    else:
        print("❌ SOME TESTS FAILED")
        if not calc_test_passed:
            print("   - Spread calculation logic has issues")
        if not ws_test_passed:
            print("   - WebSocket data simulation failed")

    print("\n📋 Summary:")
    print("• Spread threshold: 1.0%")
    print("• Alerts trigger when |spread| >= 1.0%")
    print("• Tested contracts: BTC_USDT (0.5%), ETH_USDT (1.9%), ADA_USDT (2.0%), SOL_USDT (0.5%), DOT_USDT (1.5%)")
    print("• Expected alerts: 3 (ETH_USDT, ADA_USDT, DOT_USDT)")


if __name__ == "__main__":
    asyncio.run(main())