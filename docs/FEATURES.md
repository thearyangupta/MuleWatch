# MuleWatch Money-Mule Features

- **Pass-through ratio:** Measures money sent out divided by money received; values close to 1.0 can indicate money rapidly passing through an account.
- **Median dwell time:** Measures the median time between incoming money and the next outgoing transaction; short dwell times can indicate rapid movement of funds.
- **Fan-in:** Counts the number of distinct accounts sending money into an account during the day.
- **Fan-out:** Counts the number of distinct accounts receiving money from an account during the day.
- **Transfer-to-cash-out chains:** Counts cash-out transactions occurring after an incoming transfer, capturing transfer followed by cash-out behaviour.
- **Account age:** Measures how many days the account has been open; newer accounts can carry higher mule risk.
- **Velocity ratio:** Compares the current day's transaction count with the account's historical daily average to identify sudden activity spikes.