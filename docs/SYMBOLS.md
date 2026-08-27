# Symbols



`ONWINCD\ONWIN.MAP` is the Borland linker map for the 16-bit `ONWIN.EXE` build,

left on the retail CD. It names the game's source modules and 1,273 of its

symbols. `ONWIN32.EXE` is the same source through the same compiler, so these

names are what the lifted 32-bit functions get called instead of `fn_0041xxxx`.



Regenerate with:



```bash

python tools/parse_map.py original/ONWINCD/ONWIN.MAP -o work/symbols.json

```



Addresses in the map are 16-bit `seg:off` into `ONWIN.EXE` and are **not** valid

in the PE. Only the names, the module boundaries and the relative code sizes

carry across.



## Modules



96 distinct CODE modules, 111 segment contributions. `_TEXT`, `_TEXTB` and

`_TEXTC` are Borland's own runtime; `W*`-prefixed modules are the Windows

portability layer the DOS game was ported onto; the rest is Operation Neptune.



| Module | Bytes | Named symbols | First few |

|---|---:|---:|---|

| `_TEXT` | 24,168 | 187 | `_abort`, `_atexit`, `_atoi` |

| `MATHPROB` | 14,620 | 12 | `_ClearAndWrite`, `_DisplayMathTitle`, `_DisplaySubConsole` |

| `_TEXTB` | 14,032 | 35 | `_RaiseException`, `_catchcleanup()`, `_rethrowexception(unsigned int,unsigned char far*)` |

| `OPENING` | 10,394 | 12 | `_Odissolve`, `_OpeningSequence`, `_delay_or_keyhit` |

| `SIGNIN` | 8,677 | 35 | `_DisplayCustomizedMessage`, `_FreeIconResources`, `_GetBlinkingKey` |

| `WGRAPHHI` | 6,713 | 35 | `_Allocate16ColorDIB`, `_CreateABitmap`, `_DrawTableCloth` |

| `LOCK` | 6,626 | 2 | `_DoCombinationLockProblem`, `_FreeLockResources` |

| `PRACTICE` | 5,312 | 3 | `_do_math_practice`, `_do_practice_customization_for_menu`, `_show_practice_score_at_bottom` |

| `NUMBERS` | 4,953 | 16 | `_Add`, `_CompactNumberToString`, `_CompactToNumber` |

| `WINDOW` | 4,659 | 8 | `_DrawWindow`, `_FlashButton`, `_RestoreBackground` |

| `GETNUM` | 4,221 | 4 | `_DisplayCalculatorErrorMessage`, `_DisplayNumber`, `_GetNumber` |

| `ACTION` | 4,220 | 3 | `_DoAction`, `_DrawSub`, `_EraseSub` |

| `CLOSING` | 3,739 | 5 | `_ExpertClosingSequence`, `_FreeClosingResources`, `_LoadClosingResources` |

| `CALC` | 3,387 | 4 | `_BlinkButton`, `_GetAnswer`, `_add_calc_mouse_regions` |

| `WFILE` | 3,345 | 20 | `_BUNDLE_ITEM`, `_GetResource`, `_LoadAndKeepResource` |

| `_TEXTC` | 3,128 | 19 | - |

| `FOES` | 3,055 | 4 | `_draw_animals`, `_erase_animals`, `_erase_with_clip` |

| `BALLAST` | 2,949 | 6 | `_CheckBallastAnswer`, `_GetBallastAnswer`, `_GetBallastHintSubst` |

| `SEARCHA` | 2,618 | 2 | `_GetSearchAreaSolutionSubst`, `_do_search_area_opening` |

| `WSTARTUP` | 2,506 | 7 | `_CleanupApp`, `_FindPreviousWindow`, `_InitApp` |

| `SUPPLY` | 2,497 | 11 | `_ClearAndWriteFast`, `_DisplaySupplyStationMessage`, `_DrawSupplyStation` |

| `ANIMLIST` | 2,439 | 10 | `_anim_playing`, `_copy2screen_anims`, `_copy2screen_clipped` |

| `WORLD` | 2,409 | 7 | `_DrawScreen`, `_FreeCommonResources`, `_FreeSectorResources` |

| `TEXTHI` | 2,394 | 8 | `_OWrapWrite`, `_WrapWrite`, `_change_string_format` |

| `CUSTOM` | 2,362 | 1 | `_do_customization` |

| `DATABANK` | 2,351 | 4 | `_DoDataBank`, `_FreeDataBankResources`, `_play_lights_on_supply` |

| `WGR` | 2,063 | 9 | `_LoadWinGDLL`, `_Rupdate_screen`, `_UnloadWinGDLL` |

| `BEZEL` | 2,051 | 8 | `_DisplayBezel`, `_DisplayInkPelletCounter`, `_DisplayOxygen` |

| `OPTIONS` | 1,842 | 13 | `_DoAboutMyProg`, `_EXit`, `_JustExit` |

| `WMIDI` | 1,587 | 9 | `_InitMIDIDriver`, `_IsMusicPlaying`, `_PlayMusic` |

| `ACCESS` | 1,538 | 6 | `_GetAccessHintString`, `_GetAccessHintSubst`, `_GetAccessSolutionString` |

| `WMAIN` | 1,524 | 4 | `_PauseAction`, `_ResumeAction` |

| `TOXLEVEL` | 1,361 | 2 | `_GetToxLevelSolutionSubst`, `_do_tox_level_opening` |

| `wgraphlo` | 1,356 | 13 | `_CopyArea256`, `_CopyPic2Pic256`, `_GetImage256` |

| `BUBBLES` | 1,175 | 6 | `_copy_area_clipped`, `_draw_bubbles`, `_erase_bubbles` |

| `LOCATE` | 1,164 | 3 | `_GetDistanceSolutionSubst`, `_do_distance_closing`, `_do_distance_opening` |

| `SOUNDHI` | 1,102 | 18 | `_FreeBackgroundMusic`, `_FreeCommonSoundEffects`, `_FreeExpertClosingMusic` |

| `FREEZER` | 1,095 | 6 | `_GetFreezerChangeSolutionSubst`, `_GetFreezerChangeTextSubst`, `_GetFreezerConvertSolutionSubst` |

| `CRACK` | 1,079 | 4 | `_GetCrackSolutionSubst`, `_GetCrackTextSubst`, `_do_crack_opening` |

| `WDLGS` | 997 | 6 | `_CenterWindow`, `_DoDialog` |

| `PIE` | 987 | 4 | `_GetPieHintSubst`, `_GetPieSolutionSubst`, `_GetPieTextSubst` |

| `WTEXTHI` | 982 | 8 | `_free_fonts`, `_get_char_width`, `_get_font` |

| `STUNGUN` | 962 | 3 | `_EraseStunGun`, `_StartStunGun`, `_UpdateStunGun` |

| `CDGLUE` | 958 | 7 | `_CheckForFile`, `_make_directories`, `_read_hof_dat` |

| `MONITOR` | 955 | 2 | `_GetCCMonitorSolutionSubst`, `_do_ccmonitor_opening` |

| `LONGLAT` | 950 | 3 | `_GetLongLatSolutionSubst`, `_GetLongLatTextSubst`, `_do_longlat_opening` |

| `CAPSULE` | 921 | 2 | `_GetCapsuleSolutionSubst`, `_do_capsule_opening` |

| `WATERTK` | 917 | 3 | `_GetWaterTankSolutionSubst`, `_do_water_tank_opening`, `_get_water_tank_number` |

| `SONAR` | 915 | 3 | `_GetSonarSolutionSubst`, `_GetSonarTextSubst`, `_do_sonar_graphics` |

| `RADIO` | 853 | 6 | `_GetRadioHintSubst`, `_GetRadioSolutionString`, `_GetRadioSolutionSubst` |

| `ONHELP` | 842 | 8 | `_do_help_educational_focus_message`, `_do_help_keyboard_message`, `_do_help_math_calculation_message` |

| `wtextlo` | 769 | 3 | `_get_char_width_asm`, `_writechar16`, `_writechar256` |

| `WWAVE` | 768 | 7 | `_InitWaveDriver`, `_IsWavePlaying`, `_KillWave` |

| `FOODSTRG` | 753 | 2 | `_GetFoodStorageSolutionSubst`, `_do_food_storage_opening` |

| `SPEED` | 711 | 2 | `_GetSpeedSolutionSubst`, `_do_speed_graphics` |

| `SIDEB` | 693 | 5 | `_GetSideBallastHintSubst`, `_GetSideBallastSolutionSubst`, `_GetSideBallastTextSubst` |

| `CLOCK` | 667 | 3 | `_GetClockSolutionSubst`, `_GetClockTextSubst`, `_do_clock_opening` |

| `DECO` | 657 | 3 | `_DrawAnimatedDecos`, `_DrawBackgroundDecos`, `_EraseAnimatedDecos` |

| `WMENU` | 644 | 5 | `_GetMenuEnabled`, `_HandleMenuMessage`, `_SetMainMenu` |

| `SISLOW` | 639 | 5 | `_GetSpeedIndSlowHintSubst`, `_GetSpeedIndSlowSolutionSubst`, `_GetSpeedIndSlowTextSubst` |

| `SIFAST` | 634 | 5 | `_GetSpeedIndFastHintSubst`, `_GetSpeedIndFastSolutionSubst`, `_GetSpeedIndFastTextSubst` |

| `WEVENT` | 622 | 5 | `_ClearEvents`, `_DoKeyEvent`, `_check_event` |

| `ROSTER` | 617 | 10 | `_FirstSectorOfZone`, `_GetGameLevel`, `_GetPastSectorMidpoint` |

| `HEATSEN` | 608 | 2 | `_GetHeatsenSolutionSubst`, `_do_heatsen_opening` |

| `NEPTUNE` | 598 | 1 | `_Main` |

| `HEADING` | 586 | 3 | `_GetHeadingSubst`, `_do_heading_closing`, `_do_heading_opening` |

| `PROBE` | 573 | 6 | `_AddProbePiece`, `_CheckProbeCollision`, `_DeleteProbePiece` |

| `SEARCHG` | 565 | 2 | `_GetSearchGridSolutionSubst`, `_do_search_grid_opening` |

| `HELP` | 549 | 1 | `_do_help` |

| `WCOLORHI` | 545 | 7 | `_SetEGAColor`, `_get_color`, `_get_invisible_color` |

| `MOUSEREG` | 539 | 7 | `_add_mouse_region`, `_check_mouse_regions`, `_clear_mouse_regions` |

| `SOUNDER` | 534 | 3 | `_GetSounderSolutionSubst`, `_do_sounder_closing`, `_do_sounder_opening` |

| `POWER` | 493 | 3 | `_GetPowerSolutionSubst`, `_GetPowerTextSubst`, `_do_power_opening` |

| `WMOUSE` | 457 | 9 | `_FreeUpMouseCursors`, `_LoadUpMouseCursors`, `_SetArrowCursor` |

| `COLLIDE` | 437 | 4 | `_AddRectangle`, `_DeleteRectangle`, `_DetectOverlap` |

| `TOXGAUGE` | 430 | 2 | `_GetToxGaugeSolutionSubst`, `_do_tox_gauge_opening` |

| `WMEMORY` | 417 | 3 | `_Free`, `_FreeJustPtr`, `_MALLOC` |

| `MATHTRIG` | 397 | 3 | `_DetectMathTrigger`, `_RefreshMathTriggers`, `_RefreshScreenMathTriggers` |

| `WTRANSIT` | 351 | 4 | `_BigBlackBothScreens`, `_dissolve`, `_fade_from_black` |

| `DEPTHG` | 346 | 2 | `_GetDepthSolutionSubst`, `_do_depthg_opening` |

| `OIL` | 344 | 2 | `_GetOilSupplySolutionSubst`, `_do_oil_supply_opening` |

| `SCALES` | 293 | 2 | `_GetScalesSolutionSubst`, `_do_scales_opening` |

| `H2O` | 288 | 3 | `_GetH2OPressureSolutionSubst`, `_GetH2OPressureTextSubst`, `_do_h2o_opening` |

| `TIMERHI` | 277 | 4 | `_check_alarm`, `_set_alarm`, `_tlc_delay` |

| `WFILEIO` | 262 | 6 | `_close_file`, `_create_directory`, `_open_file_for_reading` |

| `MAINMENU` | 262 | 2 | `_InitializeMainMenu`, `_InitializePracticeMainMenu` |

| `NUM` | 192 | 1 | `_check_num` |

| `MAP` | 159 | 1 | `_DoMapScreen` |

| `WNEPRES` | 119 | 2 | `_free_real_rsrc_nums`, `_load_real_rsrc_nums` |

| `MIDI` | 57 | 3 | `_PauseSound`, `_ResetSoundPause`, `_ResumeSound` |

| `EVENTHI` | 34 | 1 | `_get_event` |

| `EDIT` | 0 | 0 | - |

| `EDITDECO` | 0 | 0 | - |

| `EDITFOES` | 0 | 0 | - |

| `EDITMATH` | 0 | 0 | - |

| `GETINT` | 0 | 0 | - |



## The level editor was compiled out



`EDIT`, `EDITDECO`, `EDITFOES`, `EDITMATH` and `GETINT` all link at **zero
bytes**. The

modules existed, the shipping build `#ifdef`-ed them away, and the linker

recorded the fact anyway. One symbol survives in the data segment:

`_editfoes_is_compiled`.



## Borland runtime symbols



215 of the 1,273 publics are Borland's own C++ runtime (`string::`,

`tstringref::`, `typeinfo::`, `operator new`, `terminate`). `parse_map.py`

leaves them in and flags them; anything not starting with `_` is not the game.



