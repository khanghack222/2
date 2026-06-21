# Telegram Bot Architecture Implementation Plan

## Overview
Transform monolithic bot.py (2845 lines) into modular architecture using 9Router patterns.

## Implementation Strategy
**Approach**: Phased implementation with testing at each stage
**Timeline**: 2-3 days of focused work
**Risk**: Medium (breaking changes to existing functionality)

## Phase 1: Foundation Layer (Day 1)

### 1.1 Create Project Structure
**Files to create**:
```
telegram_bot/
├── config.py
├── main.py
├── core/
│   ├── __init__.py
│   ├── app.py
│   ├── context.py
│   ├── plugin.py
│   └── middleware.py
├── data/
│   ├── __init__.py
│   ├── database.py
│   ├── repositories.py
│   └── migrations.py
├── services/
│   ├── __init__.py
│   └── cache.py
```

**Tasks**:
- [ ] Create directory structure
- [ ] Implement config.py with environment loading and validation
- [ ] Create main.py entry point
- [ ] Implement core/context.py (AppContext container)
- [ ] Implement core/middleware.py (MiddlewarePipeline)
- [ ] Implement core/plugin.py (plugin registry)
- [ ] Refactor data/database.py to new structure
- [ ] Implement data/repositories.py (repository pattern)
- [ ] Implement services/cache.py (CacheService class)

**Dependencies**: None (foundation layer)

**Validation**: 
- Python syntax check
- Import validation
- Config loading test

### 1.2 Implement AI System
**Files to create**:
```
ai/
├── __init__.py
├── provider.py
├── router.py
├── history.py
└── providers/
    ├── __init__.py
    ├── ninerouter.py
    ├── groq.py
    └── openai_provider.py
```

**Tasks**:
- [ ] Implement ai/provider.py (BaseProvider interface, ProviderResponse)
- [ ] Implement ai/router.py (AIRouter with fallback logic)
- [ ] Implement ai/history.py (ChatHistory with token estimation)
- [ ] Implement 9Router provider (ninerouter.py)
- [ ] Implement Groq provider (groq.py)
- [ ] Implement OpenAI provider (openai_provider.py)
- [ ] Add circuit breaker logic to router.py

**Dependencies**: Phase 1.1 (config, context)

**Validation**:
- Provider instantiation test
- Mock API call test
- Fallback logic test

### 1.3 Implement HTTP Client
**Files to create**:
```
http/
├── __init__.py
└── client.py
```

**Tasks**:
- [ ] Implement HttpClient class with connection pooling
- [ ] Add health tracking (EndpointHealth)
- [ ] Implement fetch_json, fetch_text, fetch_bytes methods
- [ ] Add timeout handling
- [ ] Add automatic retry for transient failures

**Dependencies**: Phase 1.1 (config)

**Validation**:
- HTTP request test
- Health metrics test
- Timeout test

### 1.4 Implement i18n System
**Files to create**:
```
i18n/
├── __init__.py
├── vi.json
└── en.json
```

**Tasks**:
- [ ] Implement Translator class in i18n/__init__.py
- [ ] Migrate all STRINGS from bot.py to vi.json and en.json
- [ ] Add placeholder support ({variable})
- [ ] Add fallback logic (user_lang → vi → key)

**Dependencies**: Phase 1.1 (config)

**Validation**:
- Translation test with placeholders
- Fallback test
- Language switching test

## Phase 2: Plugin System (Day 2)

### 2.1 Create Base Plugin Infrastructure
**Files to create**:
```
plugins/
├── __init__.py
└── base.py
```

**Tasks**:
- [ ] Implement BasePlugin abstract class
- [ ] Define CommandInfo and MenuSection dataclasses
- [ ] Add helper methods (t(), reply(), edit())
- [ ] Update core/plugin.py to discover and load plugins

**Dependencies**: Phase 1 complete

**Validation**:
- Plugin discovery test
- Plugin instantiation test

### 2.2 Implement First Plugin: system.py
**Files to create**:
```
plugins/system.py
```

**Tasks**:
- [ ] Migrate handlers: start, help, id, status, restart, lang, cancel
- [ ] Implement menu system integration
- [ ] Register commands with CommandInfo
- [ ] Add menu_section() with categories

**Dependencies**: Phase 2.1

**Validation**:
- Manual test: /start, /help, /id, /status, /lang
- Menu navigation test

### 2.3 Implement Utility Plugins
**Files to create**:
```
plugins/utility.py
```

**Tasks**:
- [ ] Migrate handlers: weather, translate, shorten, qr, ip, screenshot, proxy, bypass
- [ ] Use HttpClient for API calls
- [ ] Use CacheService for caching
- [ ] Apply @rate_limit decorators

**Dependencies**: Phase 2.1, 1.3

**Validation**:
- Test each command individually
- Test rate limiting
- Test cache behavior

### 2.4 Implement Tool Plugins
**Files to create**:
```
plugins/tools.py
```

**Tasks**:
- [ ] Migrate handlers: calc, password, passwords, password_reset, password_generate, password_delete, password_list, code
- [ ] Port safe_eval logic
- [ ] Port Fernet encryption logic
- [ ] Add proper error handling

**Dependencies**: Phase 2.1

**Validation**:
- Test calculator with various expressions
- Test password generation/encryption
- Test code command

### 2.5 Implement Remaining Plugins
**Files to create**:
```
plugins/finance.py
plugins/education.py
plugins/entertainment.py
plugins/calendar.py
plugins/tiktok.py
plugins/media.py
plugins/admin.py
plugins/stats.py
```

**Tasks**:
- [ ] Migrate crypto, stock, tygia → finance.py
- [ ] Migrate van, dictionary, wiki → education.py
- [ ] Migrate joke, anime, meme → entertainment.py
- [ ] Migrate remind, list, lich → calendar.py
- [ ] Migrate all TikTok handlers → tiktok.py
- [ ] Migrate yt, music, news → media.py
- [ ] Migrate admin commands → admin.py
- [ ] Migrate stats commands → stats.py

**Dependencies**: Phase 2.1

**Validation**:
- Test each plugin category
- Test cross-plugin interactions

## Phase 3: Integration & Testing (Day 3)

### 3.1 Wire Everything Together
**Files to modify**:
```
core/app.py
main.py
```

**Tasks**:
- [ ] Initialize all services in core/app.py
- [ ] Create AppContext with all dependencies
- [ ] Load all plugins via plugin registry
- [ ] Register all plugin handlers
- [ ] Setup middleware pipeline
- [ ] Initialize HTTP client
- [ ] Initialize i18n system
- [ ] Setup shutdown hooks

**Dependencies**: Phase 2 complete

**Validation**:
- Full startup test
- Plugin discovery test
- Handler registration test

### 3.2 Add Middleware Pipeline
**Files to create**:
```
core/middlewares/
├── __init__.py
├── flood_protection.py
├── rate_limit.py
├── stats_logger.py
└── error_handler.py
```

**Tasks**:
- [ ] Implement FloodProtection middleware
- [ ] Implement RateLimit middleware
- [ ] Implement StatsLogger middleware
- [ ] Implement ErrorHandler middleware
- [ ] Wire middlewares into pipeline
- [ ] Add periodic cleanup task

**Dependencies**: Phase 3.1

**Validation**:
- Test flood protection
- Test rate limiting
- Test stats logging
- Test error handling

### 3.3 Implement Menu System
**Files to create**:
```
core/menu.py
```

**Tasks**:
- [ ] Implement MenuManager class
- [ ] Add section registration
- [ ] Add keyboard generation (main_menu_keyboard, section_keyboard)
- [ ] Add callback handler for menu interactions
- [ ] Integrate with plugins

**Dependencies**: Phase 3.1, 3.2

**Validation**:
- Test menu navigation
- Test all menu buttons
- Test back button

### 3.4 Update Dashboard
**Files to modify**:
```
dashboard.py
```

**Tasks**:
- [ ] Add AI provider health metrics endpoint
- [ ] Add HTTP client health metrics endpoint
- [ ] Add middleware stats endpoint
- [ ] Add cache stats endpoint
- [ ] Update dashboard UI to show new metrics

**Dependencies**: Phase 3.1

**Validation**:
- Test all dashboard endpoints
- Verify health metrics display

### 3.5 Comprehensive Testing
**Tasks**:
- [ ] Test all 40+ commands
- [ ] Test error scenarios
- [ ] Test rate limiting
- [ ] Test flood protection
- [ ] Test AI fallback
- [ ] Test circuit breaker
- [ ] Test HTTP client health tracking
- [ ] Test i18n switching
- [ ] Test menu navigation
- [ ] Test dashboard

**Dependencies**: Phase 3.4

**Validation**:
- All tests pass
- No regressions from original bot

## Phase 4: Cleanup & Documentation

### 4.1 Remove Legacy Code
**Tasks**:
- [ ] Backup original bot.py
- [ ] Remove old bot.py (after full testing)
- [ ] Update requirements.txt
- [ ] Update Dockerfile if needed
- [ ] Update docker-compose.yml if needed

**Dependencies**: Phase 3.5

### 4.2 Documentation
**Tasks**:
- [ ] Update README.md with new architecture
- [ ] Add architecture diagram
- [ ] Document plugin development guide
- [ ] Document configuration options
- [ ] Document deployment changes

**Dependencies**: Phase 4.1

## Key Design Decisions

### 1. Plugin Discovery
**Decision**: Use importlib to scan plugins/ directory
**Rationale**: Automatic, no manual registration needed
**Trade-off**: Less explicit, but simpler to maintain

### 2. Middleware Pipeline
**Decision**: Linear pipeline with next() pattern
**Rationale**: Simple, predictable, easy to debug
**Trade-off**: Less flexible than tree-based, but sufficient for our needs

### 3. Dependency Injection
**Decision**: Manual DI via AppContext
**Rationale**: No need for complex DI framework
**Trade-off**: More boilerplate, but simpler and more explicit

### 4. HTTP Client
**Decision**: Single shared session with connection pooling
**Rationale**: Reuse connections, better performance
**Trade-off**: Need careful session management

### 5. i18n Storage
**Decision**: JSON files in i18n/ directory
**Rationale**: Easy to edit, version control friendly
**Trade-off**: Slightly slower than in-memory dict, but acceptable

## Risk Mitigation

### Risk: Breaking existing functionality
**Mitigation**: 
- Keep original bot.py until full testing complete
- Test each plugin individually before integration
- Implement plugins incrementally (one at a time)

### Risk: Performance regression
**Mitigation**:
- Profile before and after
- Use connection pooling
- Keep cache layer

### Risk: Complexity increase
**Mitigation**:
- Clear documentation
- Consistent patterns
- Code reviews during implementation

## Success Criteria

- [ ] All 40+ commands work as before
- [ ] No performance regression
- [ ] Code is more maintainable (measured by file sizes < 300 lines)
- [ ] Tests pass
- [ ] Documentation complete
- [ ] Dashboard shows health metrics

## Timeline

**Day 1**: Foundation layer (config, data, services, AI, HTTP, i18n)
**Day 2**: Plugin system (base, all plugins)
**Day 3**: Integration & testing
**Day 4**: Cleanup & documentation (if needed)

## Conclusion

This plan breaks down the massive refactor into manageable phases with clear validation points. Each phase builds on the previous one, allowing for incremental testing and risk mitigation.
