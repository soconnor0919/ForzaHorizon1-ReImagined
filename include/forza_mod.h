// Experimental native mod ABI. No C++ objects or guest pointers cross this boundary.
#pragma once
#include <stdint.h>

#define FORZA_MOD_ABI 1u
#define FORZA_MOD_PRESENTATION 1u
#define FORZA_MOD_HUD_SCALE 1u

typedef struct ForzaModHost {
  uint32_t size;
  uint32_t abi;
  uint32_t capabilities;
  uint32_t reserved;
  void (*log)(const char* message);
} ForzaModHost;

typedef struct ForzaModFrame {
  uint32_t size;
  uint32_t output_width;
  uint32_t output_height;
  uint32_t reserved;
  uint64_t number;
} ForzaModFrame;

typedef struct ForzaModPresentation {
  uint32_t size;
  uint32_t flags;  // FORZA_MOD_PRESENTATION: this mod requests presentation changes.
  uint32_t letterbox;
  float hud_horizontal_scale;  // 1 = unchanged; >1 centers the HUD in a narrower area.
} ForzaModPresentation;

enum ForzaModView { FORZA_VIEW_OTHER, FORZA_VIEW_GAMEPLAY, FORZA_VIEW_MAP };
typedef struct ForzaModProjection {
  uint32_t size;
  uint32_t view;
  uint32_t viewport_width;
  uint32_t viewport_height;
  double aspect;
} ForzaModProjection;

typedef struct ForzaMod {
  uint32_t size;
  uint32_t abi;
  const char* name;
  void (*frame)(const ForzaModFrame*, ForzaModPresentation*);
  void (*projection)(ForzaModProjection*);
} ForzaMod;

// Export with C linkage. The table and callbacks must live for the process lifetime.
typedef const ForzaMod* (*ForzaModInitialize)(const ForzaModHost*, const char* mod_directory);
