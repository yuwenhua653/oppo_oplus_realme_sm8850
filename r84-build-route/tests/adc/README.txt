R84 ADC lifecycle fixture

Run with Python 3 and a C compiler providing pthread, AddressSanitizer and
UndefinedBehaviorSanitizer:
  python run_lifecycle.py --source /absolute/candidate.c --output /fresh/evidence

The runner extracts complete production function bodies, enums, structures and
register constants from the supplied exact C file. It does not rewrite those
bodies. Probe, ISR, thermal-zone registration, both TM workers, notification
work, conversions, thermal callbacks, IIO reads, lifecycle helpers and PM entry
points are actual extracted code. RESULT.json binds source SHA256, extracted
function names and all four executable fixture inputs.

Mocked portions: DT parsing supplies four synthetic channels/two SDAMs; hardware
register reads/writes, handshake poll, scaling and the IRQ/devres/IIO/thermal API
implementations are host substitutes. Thermal registration invokes actual
get_temp and set_trips callbacks, including immediate completion IRQs. Work runs
only when explicitly drained except the two controlled pthread cases. Device
managed storage remains alive until the explicit simulated unregister stage.

26 scenarios:
- 6 startup cases: IRQ during either IRQ request, during either thermal-zone
  registration, before final IIO registration, and immediate EOC completion.
- 14 failures: either IRQ request, either thermal registration, final IIO
  registration, DT allocation returning no channel array, and eight allocation
  failure positions. IRQ ownership, list publication, pending work, request
  queues and IPC cleanup are checked where applicable.
- 1 stop case: an IRQ at cancellation, late cached-temperature/set_trips/IIO
  callbacks after STOPPING, and repeated cleanup.
- 3 PM cases: either IRQ request failing during restore and a pending
  nonthermal notification across suspend/resume.
- 2 controlled concurrency cases use the actual quiesce helper directly, while
  normal freeze/restore wrappers are covered by the PM cases. First, a running
  TM worker pauses after clearing a whole SDAM status under adc.lock; the stop
  thread closes tm_ready and enters work cancellation before the worker is
  released. Both channel notifications must still complete. Second, an
  immediate conversion holds adc.lock while awaiting EOC; the quiesce thread
  reaches the adc.lock acquisition fence after global-work cancellation before
  EOC is delivered. Completion IRQs must remain owned until the conversion has
  read its data. Condition-variable latches force these interleavings rather
  than relying on thread creation order.

The original negative run compiles the original whole probe and ISR, injects the
same IRQ before the first request_irq returns, and must fail at the specific
"work queued before INIT_WORK" runtime assertion. A random crash or compiler
failure is not accepted as the regression proof:
  python run_lifecycle.py --original --source /absolute/original.c --output /fresh/original-evidence

Limitations: the fixture is not a Linux kernel, DT parser, interrupt controller,
weak-memory model, exhaustive race exploration, or hardware test. It does not
qualify external raw ADC consumer lifetime or unrelated nonthermal allocation
semantics. No TSan/lockdep was run. LeakSanitizer is disabled for fixture kernel
primitives; ASan/UBSan and Werror are enabled. Real target compilation, retained
kernel ABI checks, finite sensor readings and device PM behavior remain separate
acceptance gates.
