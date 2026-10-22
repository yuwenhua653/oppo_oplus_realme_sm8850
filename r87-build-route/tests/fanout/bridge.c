/* Actual BQ and strategy setter bodies precede this bridge. All errors below
 * are transport-stub errors; the real two-provider fanout and cache run above. */
static int platform_fg_ops_set_fastcharge(unsigned role,bool en) { assert(role<2);provider_calls[role]++;return fg_set_fastcharge_mode(&chips[role],en); }
static int strategy_class_fg_set_fastcharge(bool en) { class_calls++;desired_mode=en;mode_at=++sequence;return strategy_fg_ops_set_fastcharge(&fg,en); }
