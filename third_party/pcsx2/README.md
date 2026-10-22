# MPEG tables and integer IDCT

`mpeg2_vlc.h` is from [PCSX2](https://github.com/PCSX2/pcsx2/blob/7fe1e5525a2c219c119aa9586cee4ceae2f54ce1/pcsx2/IPU/mpeg2_vlc.h), commit `7fe1e5525a2c219c119aa9586cee4ceae2f54ce1`.

Its original GPL-2.0-or-later and libmpeg2 copyright notices are retained. The combined project is distributed under GPL-3.0-or-later; see [COPYING](../../COPYING). The only portability edit replaces the PCSX2-specific `s8` cast with `std::int8_t`.

`ipu_idct.h` adapts the scalar integer IDCT from [IPU_MultiISA.cpp](https://github.com/PCSX2/pcsx2/blob/7fe1e5525a2c219c119aa9586cee4ceae2f54ce1/pcsx2/IPU/IPU_MultiISA.cpp) at the same revision, retaining its GPL-2.0-or-later and libmpeg2 notices. Portability changes use standard integer types and `std::array`, replace aliased 32-bit stores with element fills, and use multiplication for negative signed inputs instead of left shifts. Coefficient permutation, integer constants and rounding follow that source.

No original game data is included.
