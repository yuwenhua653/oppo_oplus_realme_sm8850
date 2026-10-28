R94 PMH0101 / MCA flashlight compatibility candidate

The retained R92 flashlight queries qti_battery_charger_get_prop for battery
resistance. The current QTI provider correctly rejects the MCA battery owner,
so the camera receives -ENODEV and a zero current budget.

The public MCA source linked in reference/PUBLIC-MODEL-SOURCE.json returns a
fixed 100000 microohm (100 milliohm) model for this property.
It is a model parameter, not measured impedance. The original flash driver
still reads battery voltage/current and computes its dynamic current budget.
The OEM zero-resistance debug-board path is not used.

The candidate restores that model locally only when the flash controller has
qcom,pmh0101-flash-led and the registered battery's parent has
mca,business_battery. SMB/IIO retains priority. Other owners still use the QTI
API and its original ownership guard. No duplicate export is added to MCA.
The device pointer is initialized for both battery-interface modes. Missing
battery data on PMH0101 fails closed; voltage/current read errors still propagate.
The final dynamic budget is clamped at zero before the camera's unsigned API.
The existing upper bound, DT channel limits, PMIC thermal/BCL/voltage protections
and all charging modules remain unchanged.

Only leds-qcom-flash.ko is a runtime candidate. Its build dependencies are not
replacement candidates. Compilation is not permission to activate a module:
check actual ELF CRCs against R92 before packaging. Keep the R92 kernel Image,
the other 294 module files and load order. Packaging must regenerate the
boot-helper hash contract for the changed LED file; swapping only the KO would
cause the existing baseline hash checks to fail. No userspace root is required.

The workflow is compile-only and creates no flashable image. Hardware behavior
must be tested after the separate ABI and packaging review. It never claims
that restoring the OEM model proves the flashlight is already fixed.
