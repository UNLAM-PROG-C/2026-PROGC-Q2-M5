// Compile-time constants for the image kernels.
#ifndef FDC_KERNELS_CONFIG_CUH
#define FDC_KERNELS_CONFIG_CUH

#define RED 0  // RGB component offsets
#define GREEN 1
#define BLUE 2
#define PIXEL_MAX 255.0f  // peak byte value, in float arithmetic
#define PIXEL_MAX_INT 255  // peak byte value, in integer arithmetic
#define BLACK 0  // black byte for out-of-image samples
#define ZERO 0.0f  // bottom of the normalized range
#define UNIT 1.0f  // top of the normalized range
#define HALF 0.5f  // half of a dimension or amplitude
#define CENTER 0.5f  // center of a normalized screen coordinate
#define SQRT2 1.41421356f  // normalize the vignette diagonal
#define MIN_STRETCH_SPAN 1.0f  // minimum contrast span in byte levels
#define GLOW_SCALE 2  // full-resolution pixels per halo sample axis
#define POSITION_FIELDS 2  // x and y per particle or confetti piece
#define PARTICLE_FIELDS 4  // RGB and radius per particle
#define PARTICLE_RADIUS 3  // column of the particle radius in pixels
#define PAPER_FIELDS 5  // RGB and two half extents per confetti piece
#define PAPER_HALF_W 3  // column of the paper half-width in pixels
#define PAPER_HALF_H 4  // column of the paper half-height in pixels
#define LAMP_FIELDS 4  // x, y, radius and power per spotlight
#define LAMP_RADIUS 2  // column of the radius in pixels
#define LAMP_POWER 3  // column of the light intensity
#define SOBEL_NEAR_WEIGHT 2.0f  // weight of the orthogonal neighbors
#define SOBEL_SCALE 0.25f  // scale of the Sobel gradient magnitude
#define HIST_INCREMENT 1  // one sample counted in a signed bin
#define HIST_INCREMENT_U 1u  // one sample counted in an unsigned bin
#define CRT_COORD_SCALE 2.0f  // maps the viewport to [-1, 1]
#define NO_SCANLINES 0  // no CRT bands when the interval is zero
#define CRT_X_MUL 1973  // hash weight of the column
#define CRT_Y_MUL 9277  // hash weight of the row
#define CRT_FRAME_MUL 26699  // hash weight of the frame
#define CRT_NOISE_MASK 255u  // extract one noise byte
#define CROWD_HASH_SHIFT_FIRST 13  // first xor-shift in the seat hash
#define CROWD_HASH_SHIFT_LAST 16  // final xor-shift in the seat hash
#define CROWD_HASH_MUL 1274126177u  // mix the shifted seat hash
#define CROWD_VAR_SHIFT 13  // extract the shirt brightness bucket
#define CROWD_JUMP_DIVISOR 7u  // separate the jump amplitude buckets
#define CROWD_HEAD_OFFSET 0.8f  // head-center offset in head radii
#define CROWD_HAIR_SHIFT 9  // extract the hair palette bucket
#define CROWD_SKIN_SHIFT 5  // extract the skin palette bucket
#define CROWD_STRIPES 3.0f  // stripes of a flag
#define CROWD_ODD_BIT 1  // alternate flag stripes and staggered rows
#define CROWD_HALVES 2  // split the stands and offset alternate rows
#define CROWD_LEFT 0  // team on the left of the stands
#define CROWD_RIGHT 1  // team on the right of the stands
#define CROWD_FLAG_BUCKET 0  // remainder of a seat hash that gets a flag

#define CH 3  // channels in packed RGB
#define GLOW_SAT_GAIN 1.5f  // scale the halo by the source saturation
#define LUMA_RED 0.299f    // BT.601 red luma weight
#define LUMA_GREEN 0.587f  // BT.601 green luma weight
#define LUMA_BLUE 0.114f   // BT.601 blue luma weight
#define BYTE_ROUND 0.5f    // round to nearest byte
#define SPOT_MAX 8  // maximum lights per pixel
#define HEAT_FREQ_Y 0.12f  // vertical wave radians per pixel
#define HEAT_SPEED_Y 18.0f  // vertical wave radians per second
#define HEAT_FREQ_X 0.09f  // horizontal wave radians per pixel
#define HEAT_SPEED_X 14.0f  // horizontal wave radians per second
#define HEAT_LATERAL 0.4f  // scale the horizontal displacement
#define CRT_NOISE_MUL 2654435761u  // integer noise multiplier
#define CRT_NOISE_SHIFT 24  // keep the high bits of the noise
#define CRT_DIAGONAL 0.70710678f  // 1/sqrt(2): normalize the vignette
#define CROWD_HASH_C 73856093u  // column hash prime
#define CROWD_HASH_R 19349663u  // row hash prime
#define CROWD_ROWS 2  // rows checked per pixel
#define CROWD_FLAG_HZ 3.2f  // flag wave radians per second
#define CROWD_FLAG_CURVE 0.30f  // flag curvature in radians per vertical pixel
#define CROWD_SHOULDER 2.0f  // torso narrowing at the shoulders in pixels
#define CROWD_POLE_W 1.0f  // flagpole half-width in pixels
#define CROWD_RISER 1.0f  // bright step edge in pixels
#define CROWD_JUMP_LOW 0.4f  // minimum jump as a fraction of the peak
#define CROWD_JUMP_SPREAD 0.6f  // extra jump fraction from the hash
#define CROWD_PHASE 0.01f  // phase radians per hash unit
#define CROWD_PHASE_TOP 628u  // roughly one cycle in hash units
#define CROWD_SPREAD 0.01f  // scale a hash bucket to 0..1
#define CROWD_SKINS 3  // skin tones in the palette
#define CROWD_HAIRS 3  // hair tones in the palette
#define CROWD_FULL 100u  // number of hash buckets

// Indices into the configuration array supplied by the host.
#define CC_W 0  // seat width in pixels
#define CC_H 1  // seat height in pixels
#define CC_JUMP 2  // jump height in pixels
#define CC_HZ 3  // jump radians per second
#define CC_GOAL_JUMP 4  // extra jump height for the scoring side
#define CC_GOAL_HZ 5  // extra jump radians per second
#define CC_WAVE 6  // flag wave amplitude in pixels
#define CC_FLAG_W 7  // flag width in pixels
#define CC_FLAG_H 8  // flag height in pixels
#define CC_FILL 9  // percent of occupied seats
#define CC_EVERY 10  // one flag every N seats
#define CC_BODY_W 11  // torso width in pixels
#define CC_BODY_H 12  // torso height in pixels
#define CC_HEAD_R 13  // head radius in pixels
#define CC_STEP 14  // step height in pixels
#define CC_POLE_H 15  // pole height above the shoulder in pixels
#define CC_SHADE_TOP 16  // shade factor for the farthest row
#define CC_SHADE_BOTTOM 17  // shade factor for the nearest row
#define CC_VAR_MIN 18  // minimum shirt brightness
#define CC_VAR_RANGE 19  // extra brightness from the hash
#define CC_HEAD_CUT 20  // fraction of the head covered by hair
#define CC_OUTLINE 21  // dark outline width in pixels
#define CC_SHOULDER_EDGE 22  // shoulder edge width in pixels
#define CC_SHOULDER_SHADE 23  // shoulder edge shade factor

// Palette rows (one RGB triple each).
#define CP_SHIRT_A 0  // left team shirt
#define CP_SHIRT_B 1  // right team shirt
#define CP_SKIN 2  // first of CROWD_SKINS skin tones
#define CP_HAIR 5  // first of CROWD_HAIRS hair tones
#define CP_TREAD 8  // step floor
#define CP_RISER 9  // dark riser
#define CP_EDGE 10  // bright step edge
#define CP_POLE 11  // flagpole
#define CP_FLAG_WHITE 12  // white flag stripe
#define CP_FLAG_A 13  // left team flag
#define CP_FLAG_B 14  // right team flag
#define CP_OUTLINE 15  // dark head outline

#endif  // FDC_KERNELS_CONFIG_CUH
