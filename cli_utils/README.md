# Some CLI Utilities for working with CNC / EDA files

## Utilities Included
* Gerber Explain
* more coming some time in the future...

## Build / Installation

_todo: migrate build process to use the `build` tool._

### To build a wheel file
* change to the directory containing both the **src** directory and the **setup.py** script
* run `python setup.py bdist_wheel`
* this will create a wheel file (.whl) in the **dist** directory

### To install from the wheel file
As always, it is recommended to install packages into a python virtual environment, as to not impact the system's python installation. _Alternatively you could install to your user directory with the --user flag on the pip install._
* activate the python virtual environment
* change directory to the **dist** directory created when build the wheel file. Or alternatively, if you downloaded the wheel file, change directory to the location of the wheel file.
* run `pip install cnc_eda_utils-1.0.0-py3-none-any.whl`
* note: update the version number in the command above that corresponds to the wheel file you built/downloaded.

### To install an editable package from source
Installing an editable package allows you to make changes to the package source code and have those changes reflected immediately in the installed pacakge. 

As always, it is recommended to install packages into a python virtual environment, as to not impact the system's python installation.
* activate the python virtual environment
* download the source code from GitHub: _URL tbd_
* change to the directory containing both the **src** directory and the **setup.py** script
* run `pip install -e .`

# Gerber Explain

This command will explain what each line of a gerber file does in (hopefully) more clear English than the gerber commands themselves.

When you install the cnc eda utils package, it will install the `grbr-exp` command. Use this command, as shown below, to access the functionality offered by the Gerber Explain command line utility.

## Options

There are some options that can be uses to suppress or display various subsets of gerber commands. To see the available options, pass the `--help` option to the command.

```shell
grbr-exp --help
```
```text
usage: Grbr To English [-h] [-s] [-a] [-d] [-f] [-p] [-t] [-c] [-S] [-A] [-C] grbr_filename

will explain what each line of a gerber file does

positional arguments:
  grbr_filename    The Name of the Gerber File to parse

options:
  -h, --help       show this help message and exit
  -a, --no-aptr    pass --no-aptr to suppress the display of grbr cmds which define an aperture
  -s, --no-state   pass --no-state to suppress the display of grbr cmds which update the graphics state
  -d, --no-draw    pass --no-draw to suppress the display of interpolate & move grbr cmds
  -f, --no-flash   pass --no-flash to suppress the display of flash grbr cmds
  -t, --with-attr  pass --with-attr to display grbr cmds which define attributes
  -p, --with-aptr  pass --with-aptr to display grbr cmds which set the current aperture
  -c, --with-cmnt  pass --with-cmnt to display comments
  -S, --attr-sum   pass --attr-sum to display the final attribute state after the file is finished parsing
  -A, --attr-hist  pass --attr-hist to display the commands executed to set/delete attributes
  -C, --cmnt-hist  pass --cmnt-hist to display the grbr file comment contents

Its better to burn out than fade away...
```

_To assist with remembering the short option names, you can place them into groups of 4, 3 and 3_
* _**asdf** - the first 4 options correspond to the 1st 4 keys in the left, middle row of the keyboard_
* _**tcp** - the next 3 options correspond to the abbreviation for one of the Internet's main communications protocol: Transmission Control Protocol_
* _**SAC** - the last 3 options, well they stand for "SAC**k**" - a sack is an object that you stuff things into_

## Sample Usage

There is 1 required positional argument and that is the file name path (absolute or relative) of the gerber file you want to parse

```shell
grbr-exp ~/Documents/PCB/KiCad/cnc_test/cnc_test-F_Cu.gbr
```
```text
----------------------------------------------------------------------------------------------------
Explaining gerber file: cnc_test-F_Cu.gbr
----------------------------------------------------------------------------------------------------
[007] SET: coordinate format integer len: 4, decimal len: 6
[010] SET: mode (units) to mm
[011] SET: level layer to dark polarity
[012] SET: interpolation mode to: linear 
[015] ADD aperture:    D10           R        ['1.800000', '1.800000']
[018] ADD aperture:    D11           C        ['1.800000']
[021] ADD aperture:    D12           C        ['0.250000']
[027] FLASH at:     18.500,     10.160         D10
[031] FLASH at:     18.500,      7.620         D11
[036] FLASH at:      6.500,     10.160         D10
[040] FLASH at:      6.500,      5.460         D11
[044] MOVE to:       6.500,     15.000       0.000,      9.540     len: 9.54
[045] LINE to:      18.500,     15.000      12.000,      0.000     len: 12.0           D12
[046] MOVE to:       6.500,     10.160     -12.000,     -4.840     len: 12.939
[047] LINE to:       6.500,     15.000       0.000,      4.840     len: 4.84           D12
[048] MOVE to:      18.500,     15.000      12.000,      0.000     len: 12.0
[049] LINE to:      18.500,     10.160       0.000,     -4.840     len: 4.84           D12
[058] ### END OF FILE ###
```
```shell
grbr-exp -sdf ~/Documents/PCB/KiCad/cnc_test/cnc_test-F_Cu.gbr
```
```text
[015] ADD aperture:    D10           R        ['1.800000', '1.800000']
[018] ADD aperture:    D11           C        ['1.800000']
[021] ADD aperture:    D12           C        ['0.250000']
[058] ### END OF FILE ###
```

### What do all those columns of output mean?

Here are some details on what each column means in the output:
1. For `SET` commands, you will get a general description of what graphics state parameter is being set and to what value.
2. For `ADD aperture` commands, you will get 
   1. the Aperture ID
   2. the Aperture Name: either a Standard Name (C - Circle, R - Rectangle, O - Obround, P - Polygon) or the name of an Aperture Macro Name
   3. the Modifiers (parameters) passed to the aperture (for example: diameter / height & width or aperture hole diameter)
3. For `MOVE to`, `LINE to`, `ARC to`, `FLASH at` commands, you will get:
   1. The X, Y coordinates specified in the command for the 1st two columns.
   2. The delta X, delta Y values from the previous location to the location specified in the command
   3. The distance between the previous location and the location specified in the command
   4. The current Aperture ID in effect for the command (not applicable for MOVE to)
4. Additionally, for `ARC to` commands you will also get
   1. The I, J center offset values specified in the command
   2. The Arc's actual center point location in absolute x, y coordinates
   3. The radius of the Arc

## Additional Development (To-Do's)
1. add sample data files & include them with the package
2. ~~add support for clockwise & counterclockwise circular interpolation mode (i.e., drawing arcs)~~ 
   1. ~~currently only linear interpolation mode (drawing line) is supported when outputting interpolation commands.~~ 
   2. ~~this includes the processing of G02, G03 (clockwise / counterclockwise interpolation mode) and G74, G75 (single / multi quadrant mode)~~ 
3. ~~add support for macro definitions (%AM)~~
4. add support for region processing
   1. currently when region mode is entered, commands are rendered the same as in non-region mode
   2. currently when region mode is exited, no regions are defined/output
   3. this includes the processing of G36 & G37
5. refactor the code separating the output logic from the parsing logic. this includes:
   1. this will enable us to support additional output formats
   2. developing an initial data model to represent the Gerber commands and file structure
   3. add support for CSV output
6. Data Model Enhancements
   1. enhance the data model to implement the use of Polarity state (%LP)
   2. enhance the data model to "attach" meta data to flashes, draws, arcs and regions 
   3. Implement Step and Repeat (%SR) ?
7. develop unit tests

# util number 2

tbd

# util number 3

tbd
