import pytest

pytestmark = pytest.mark.integration


class DummyEvent:
    def __init__(self, name, payload=None):
        self.name = name
        self.payload = payload or {}


class DummyEventBus:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)

    def get_events(self, name=None):
        if name:
            return [e for e in self.events if e.name == name]
        return self.events


class DummyDataProvider:
    def __init__(self):
        self.data = [{"price": 100}, {"price": 101}, {"price": 102}]
        self.index = 0

    async def get_next(self):
        if self.index < len(self.data):
            d = self.data[self.index]
            self.index += 1
            return d
        return None


class DummyBalanceManager:
    def __init__(self, initial=1000):
        self.balance = initial
        self.history = [initial]

    def update(self, amount):
        self.balance += amount
        self.history.append(self.balance)

    def get_balance(self):
        return self.balance


class DummyMarketSimulator:
    def __init__(self, event_bus, balance_manager):
        self.event_bus = event_bus
        self.balance_manager = balance_manager
        self.orders = []

    async def execute_order(self, order):
        # Simulate order execution and balance update
        if order["type"] == "buy":
            self.balance_manager.update(-order["amount"] * order["price"])
        elif order["type"] == "sell":
            self.balance_manager.update(order["amount"] * order["price"])
        self.orders.append(order)
        self.event_bus.publish(DummyEvent("order_executed", order))


class DummyStrategy:
    def __init__(self, event_bus):
        self.event_bus = event_bus
        self.orders = []

    async def on_data(self, data):
        # Simple strategy: buy if price is even, sell if price is odd
        if data["price"] % 2 == 0:
            order = {"type": "buy", "amount": 1, "price": data["price"]}
        else:
            order = {"type": "sell", "amount": 1, "price": data["price"]}
        self.orders.append(order)
        self.event_bus.publish(DummyEvent("order_created", order))
        return order


class DummyEnvironment:
    def __init__(self):
        self.event_bus = DummyEventBus()
        self.data_provider = DummyDataProvider()
        self.balance_manager = DummyBalanceManager()
        self.market = DummyMarketSimulator(self.event_bus, self.balance_manager)
        self.strategy = DummyStrategy(self.event_bus)

    async def run(self):
        while True:
            data = await self.data_provider.get_next()
            if not data:
                break
            order = await self.strategy.on_data(data)
            await self.market.execute_order(order)


@pytest.mark.asyncio
async def test_environment_initialization_and_workflow():
    """
    Test full environment initialization and end-to-end workflow.
    """
    env = DummyEnvironment()
    assert env.balance_manager.get_balance() == 1000
    assert env.event_bus.get_events() == []
    assert env.market.orders == []
    assert env.strategy.orders == []

    await env.run()

    # Check that all data points were processed
    assert len(env.strategy.orders) == 3
    assert len(env.market.orders) == 3

    # Check event system integration
    order_created_events = env.event_bus.get_events("order_created")
    order_executed_events = env.event_bus.get_events("order_executed")
    assert len(order_created_events) == 3
    assert len(order_executed_events) == 3

    # Check balance management
    # Initial: 1000, buy at 100 (-100), sell at 101 (+101), buy at 102 (-102)
    # Final: 1000 - 100 + 101 - 102 = 899
    assert env.balance_manager.get_balance() == 899
    assert env.balance_manager.history == [1000, 900, 1001, 899]


@pytest.mark.asyncio
async def test_error_handling_across_components():
    """
    Test error handling when data provider runs out of data.
    """
    env = DummyEnvironment()
    # Exhaust data provider
    await env.run()
    # Try running again, should not raise
    await env.run()
    # No new orders should be created
    assert len(env.strategy.orders) == 3


@pytest.mark.asyncio
async def test_async_coordination_and_event_flow():
    """
    Test async event flow and coordination between components.
    """
    env = DummyEnvironment()
    # Patch event bus to record event order
    event_order = []
    orig_publish = env.event_bus.publish

    def record_publish(event):
        event_order.append(event.name)
        orig_publish(event)

    env.event_bus.publish = record_publish

    await env.run()
    # Events should alternate order_created/order_executed
    assert event_order == [
        "order_created",
        "order_executed",
        "order_created",
        "order_executed",
        "order_created",
        "order_executed",
    ]
