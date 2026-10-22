// SPDX-FileCopyrightText: 2002-2026 PCSX2 Dev Team
// SPDX-License-Identifier: GPL-2.0-or-later
// Based on libmpeg2: Copyright (C) 2000-2002 Michel Lespinasse
// and Copyright (C) 1999-2000 Aaron Holtzman.
// Scalar IDCT adapted from PCSX2 commit7fe1e5525a2c219c119aa9586cee4ceae2f54ce1.
// Portability changes: standard integer types, no aliased 32-bit accesses,
// multiplication instead of shifting negative signed inputs, std::array input.
#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
namespace yakuza::ipu_math {
inline constexpr int W1=2841, W2=2676, W3=2408, W5=1609, W6=1108, W7=565;
inline void butterfly(int& t0, int& t1, int w0, int w1, int d0, int d1)
{
	int tmp = w0 * (d0 + d1);
	t0 = tmp + (w1 - w0) * d1;
	t1 = tmp - (w1 + w0) * d0;
}

inline void inverseDct(std::array<int16_t, 64>& data)
{
    auto* block = data.data();
	for (int i = 0; i < 8; i++)
	{
		int16_t* const rblock = block + 8 * i;
        if (std::all_of(rblock+1, rblock+8, [](int16_t v) { return v == 0; }))
        {
            std::fill_n(rblock, 8, int16_t(int(rblock[0]) * 8));
            continue;
        }

		int a0, a1, a2, a3;
		{
			const int d0 = (int(rblock[0]) * 2048) + 128;
			const int d1 = rblock[1];
			const int d2 = int(rblock[2]) * 2048;
			const int d3 = rblock[3];
			int t0 = d0 + d2;
			int t1 = d0 - d2;
			int t2, t3;
			butterfly(t2, t3, W6, W2, d3, d1);
			a0 = t0 + t2;
			a1 = t1 + t3;
			a2 = t1 - t3;
			a3 = t0 - t2;
		}

		int b0, b1, b2, b3;
		{
			const int d0 = rblock[4];
			const int d1 = rblock[5];
			const int d2 = rblock[6];
			const int d3 = rblock[7];
			int t0, t1, t2, t3;
			butterfly(t0, t1, W7, W1, d3, d0);
			butterfly(t2, t3, W3, W5, d1, d2);
			b0 = t0 + t2;
			b3 = t1 + t3;
			t0 -= t2;
			t1 -= t3;
			b1 = ((t0 + t1) * 181) >> 8;
			b2 = ((t0 - t1) * 181) >> 8;
		}

		rblock[0] = (a0 + b0) >> 8;
		rblock[1] = (a1 + b1) >> 8;
		rblock[2] = (a2 + b2) >> 8;
		rblock[3] = (a3 + b3) >> 8;
		rblock[4] = (a3 - b3) >> 8;
		rblock[5] = (a2 - b2) >> 8;
		rblock[6] = (a1 - b1) >> 8;
		rblock[7] = (a0 - b0) >> 8;
	}

	for (int i = 0; i < 8; i++)
	{
		int16_t* const cblock = block + i;

		int a0, a1, a2, a3;
		{
			const int d0 = (int(cblock[8 * 0]) * 2048) + 65536;
			const int d1 = cblock[8 * 1];
			const int d2 = int(cblock[8 * 2]) * 2048;
			const int d3 = cblock[8 * 3];
			const int t0 = d0 + d2;
			const int t1 = d0 - d2;
			int t2;
			int t3;
			butterfly(t2, t3, W6, W2, d3, d1);
			a0 = t0 + t2;
			a1 = t1 + t3;
			a2 = t1 - t3;
			a3 = t0 - t2;
		}

		int b0, b1, b2, b3;
		{
			const int d0 = cblock[8 * 4];
			const int d1 = cblock[8 * 5];
			const int d2 = cblock[8 * 6];
			const int d3 = cblock[8 * 7];
			int t0, t1, t2, t3;
			butterfly(t0, t1, W7, W1, d3, d0);
			butterfly(t2, t3, W3, W5, d1, d2);
			b0 = t0 + t2;
			b3 = t1 + t3;
			t0 = (t0 - t2) >> 8;
			t1 = (t1 - t3) >> 8;
			b1 = (t0 + t1) * 181;
			b2 = (t0 - t1) * 181;
		}

		cblock[8 * 0] = (a0 + b0) >> 17;
		cblock[8 * 1] = (a1 + b1) >> 17;
		cblock[8 * 2] = (a2 + b2) >> 17;
		cblock[8 * 3] = (a3 + b3) >> 17;
		cblock[8 * 4] = (a3 - b3) >> 17;
		cblock[8 * 5] = (a2 - b2) >> 17;
		cblock[8 * 6] = (a1 - b1) >> 17;
		cblock[8 * 7] = (a0 - b0) >> 17;
	}
}


}
