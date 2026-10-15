#include "native_mods.h"
#include "../../include/forza_mod.h"
#include <rex/logging.h>
#include <rex/cvar.h>
#include <atomic>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <mutex>
#include <string>
#include <vector>
#ifdef _WIN32
#include <windows.h>
#else
#include <dlfcn.h>
#endif

namespace forza::mods {
namespace {
std::vector<const ForzaMod*> plugins;
std::function<void(bool, float)> apply_presentation;
std::atomic<uint64_t> output_size{};
uint64_t frame_number = 0;
std::mutex frame_mutex;
void Log(const char* text) { if (text) REXLOG_INFO("Native mod: {}", text); }
ForzaModHost host{sizeof(ForzaModHost), FORZA_MOD_ABI, 0, 0, Log};
}

void Initialize(std::function<void(bool, float)> presentation) {
  apply_presentation = std::move(presentation);
  const char* paths = std::getenv("FORZA_NATIVE_MODS");
  if (!paths || !*paths) return;
  bool hud_scale = false, source_aspect = false;
  for (const auto& flag : rex::cvar::GetRegistry()) {
    hud_scale |= flag.name == "forza_hud_horizontal_scale";
    source_aspect |= flag.name == "forza_present_16_9";
  }
  if (hud_scale && source_aspect) host.capabilities |= FORZA_MOD_HUD_SCALE;
#ifdef _WIN32
  constexpr char separator = ';';
#else
  constexpr char separator = ':';
#endif
  const std::string list(paths);
  size_t begin = 0;
  while (begin < list.size()) {
    const size_t end = list.find(separator, begin);
    const auto entry = list.substr(begin, end - begin);
    const std::filesystem::path path(std::u8string(entry.begin(), entry.end()));
    begin = end == std::string::npos ? list.size() : end + 1;
    std::error_code error;
    if (!path.is_absolute() || !std::filesystem::is_regular_file(path, error)) {
      REXLOG_WARN("Native mod path is not an absolute library file: {}", path.string());
      continue;
    }
#ifdef _WIN32
    auto library = LoadLibraryExW(path.c_str(), nullptr,
        LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
    auto initialize = library ? reinterpret_cast<ForzaModInitialize>(
        GetProcAddress(library, "ForzaModInit")) : nullptr;
#else
    auto library = dlopen(path.c_str(), RTLD_NOW | RTLD_LOCAL);
    auto initialize = library ? reinterpret_cast<ForzaModInitialize>(
        dlsym(library, "ForzaModInit")) : nullptr;
#endif
    if (!initialize) {
      REXLOG_WARN("Could not load native mod entry point: {}", path.string());
      continue;
    }
    const auto directory_u8 = path.parent_path().u8string();
    const auto* mod = initialize(&host, reinterpret_cast<const char*>(directory_u8.c_str()));
    if (!mod || mod->size != sizeof(ForzaMod) || mod->abi != FORZA_MOD_ABI || !mod->name) {
      REXLOG_WARN("Native mod rejected ABI {}: {}", FORZA_MOD_ABI, path.string());
      continue;
    }
    // Libraries remain mapped: a callback may still be executing on a guest thread.
    plugins.push_back(mod);
    REXLOG_INFO("Loaded native mod: {}", mod->name);
  }
}

void Resize(uint32_t width, uint32_t height) {
  output_size.store((uint64_t(width) << 32) | height, std::memory_order_relaxed);
}

void Frame() {
  if (plugins.empty()) return;
  std::lock_guard lock(frame_mutex);
  const auto size = output_size.load(std::memory_order_relaxed);
  ForzaModFrame frame{sizeof(frame), uint32_t(size >> 32), uint32_t(size), 0, ++frame_number};
  for (auto* mod : plugins) {
    if (!mod->frame) continue;
    ForzaModPresentation request{sizeof(request), 0, 1, 1.0f};
    mod->frame(&frame, &request);
    if ((request.flags & FORZA_MOD_PRESENTATION) && std::isfinite(request.hud_horizontal_scale) &&
        request.hud_horizontal_scale >= 1.0f && request.hud_horizontal_scale <= 4.0f &&
        apply_presentation) {
      apply_presentation(request.letterbox != 0, request.hud_horizontal_scale);
    }
  }
}

double Projection(uint32_t view, uint32_t width, uint32_t height, double aspect) {
  ForzaModProjection event{sizeof(event), view, width, height, aspect};
  for (auto* mod : plugins) {
    if (mod->projection) mod->projection(&event);
    if (!std::isfinite(event.aspect) || event.aspect < 0.1 || event.aspect > 10.0) {
      event.aspect = aspect;
    }
  }
  return event.aspect;
}
}
