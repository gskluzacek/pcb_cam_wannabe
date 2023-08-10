import os
import sys
import argparse
import re
from collections import namedtuple
from typing import Iterable, Iterator, Any


# TODO: A code number can be padded with leading zeros, but the resulting number record must not contain more
#  than 10 digits. The conventional representation of a code number contains exactly two digits, so if the
#  number is less than 10, it is padded with one leading zero.

# TODO: the spec says that Gerber Files are pure 7-bit ascii files.
#   files are may contain unicode code points less than 65,536 by using unicode 65,536 sequences
#   the format should be: \uXXXX
#   where X is a hex-digit
#   the escape sequence must be 4 hex-digits long
#   ? do we need specify 7-bit ascii as the encoding when reading in files and then do escape string replacement?

# global variables that are used to control the output display options
(
    ATTRIB_DISP,
    COMMENT_DISP,
    STATE_DISP,
    APRTR_ADD_DISP,
    APRTR_SET_DISP,
    FLASH_DISP,
    DRAW_DISP,
    HIST_ATTRIB_DISP,
    HIST_COMMENT_DISP,
    ATTRIB_SUM_DISP,
) = [None] * 10


class GrbrCoordSys:
    def __init__(self, int_len: int, dec_len: int, zero_supp: str = "L", units: str = None):
        """Create a Gerber Coordinate System Object - handles parsing coordinate values

        :param int_len:         in a coordinate, how many digits before the decimal (the integer portion)
        :param dec_len:         in a coordinate, how many digits after the decimal (the decimal portion)
        :param zero_supp:       the type of zero suppression used (L default T deprecated, D not valid)
        :param units:           the units that the coordinates are in (MM - metric, IN - empirical)
        """
        self.int_len = int_len
        self.dec_len = dec_len
        self.tot_len = self.int_len + self.dec_len
        self.zero_supp = zero_supp
        self.units = units

    def parse_grbr_coord(self, grbr_coord: str) -> float:
        """Takes a gerber file coordinate as a string and parses it to a float.

        :param grbr_coord: the gerber file coordinate to be parsed
        :return: the parsed gerber file coordinate as a floating point number

        gerber file coordinate are specified as a strings without a decimal point, so they
        must be converted to a floating point number with the appropriate number of digits
        before and after the decimal point. The %FS gerber command specifies the number of
        digits before and after the decimal point and must be parsed and the GrbrCoordSys
        must be created before calling this method.

        Even though the current Gerber specification only support leading zero suppression (L),
        this function can also handle trailing zero suppression (T - deprecated) as well as no
        suppression (D - invalid per the spec).
        """
        # remove any leading + or - sign and set the multiplier accordingly
        multiplier, grbr_coord = (
            (1, grbr_coord) if grbr_coord[0] not in ("-", "+") else (int(grbr_coord[0] + "1"), grbr_coord[1:])
        )
        # set the position to start parsing at after padding both start and end with zeros
        start_pos = self.tot_len if self.zero_supp == "T" else len(grbr_coord)
        # pad both the start and end of the coordinate with zeros, then take the tot_len chars from the middle
        parsed_string = f"{'0' * self.tot_len}{grbr_coord}{'0' * self.tot_len}"[start_pos : start_pos + self.tot_len]
        # insert the decimal point int_len characters into the parsed string, cast to a float and set the sign
        return multiplier * float(f"{parsed_string[:self.int_len]}.{parsed_string[self.int_len:]}")

    def set_units(self, units: str) -> None:
        """Set the units that the coordinates are in.

        :param units: MM - metric, IN - empirical
        """
        self.units = units


class GrbrPlot:
    """
    list of deprecated commands:
    ----------------------------
    G54 - Select aperture*
    G55 - Prepare for flash
    G70 - set units to inches*
    G71 - set units to mm*
    G90 - set coordinate format to absolute
    G91 - set coordinate format to incremental
    M00 - program stop (same as M02)
    M01 - option stop
    AS - Sets the ‘Axes correspondence’ graphics state parameter [5]
         %AS(AXBY|AYBX)*%
    IN - Sets the name of the file image
         %IN<Name>*%
    IP - Sets the ‘Image polarity’ graphics state parameter
         %IP(POS|NEG)*%
    IR - Sets ‘Image rotation’ graphics state parameter [4]
         %IR(0|90|180|270)*%
    MI - Sets ‘Image mirroring’ graphics state parameter [1]
         documentation advises to: "avoid like the plague"
         %MI[A(0|1)][B(0|1)]*%
         where 1 is enabled and 0 is disabled
         A1 --> the image will be flipped along the B axis
         B1 --> the image will be flipped along the A axis
    OF - Sets ‘Image offset’ graphics state parameter [3]
         %OF[A<+/-Offset>][B<+/-Offset>]*%
         offsets are in the units set by MO
         offsets must be between 0 and 99999.99999
    SF - Sets ‘Scale factor’ graphics state parameter
         SF[A<Factor>][B<Factor>]*
         factor is between 0.0001 ≤ and ≤ 999.99999
    LN - Level Name, has no effect on the image. It is no more than a comment about the level (should iuse G04 instead)
         %LN<Name>*%

    data without an explicit operation code
    ---------------------------------------
    Coordinates without an operation code are deprecated.

    Previous versions of the specification allowed coordinate data without explicit operation code. Per
    the specification, this was only allowed after a D01 command was issued. Any use of any other Dnn
    Cmd (D02, D03, aperture selection) then canceled this implicit D01 operator.

    A D01 code sets the operation mode to interpolate. It remains in interpolate till any other D code is
    encountered. In sequences of D01 operations this allows omitting an explicit D01 code after the first operation.

    Example:
    D10*
    X700Y1000D01*
    X1200Y1000*
    X1200Y1300*
    D11*
    X1700Y2000D01*
    X2200Y2000*
    X2200Y2300*

    The operation mode is only defined after a D01. The operation mode after a D02, D03 or an
    aperture selection (Dnn with nn≥10) is undefined. Therefore a file containing coordinates
    without operation code after a D03 or an aperture selection (Dnn with nn≥10) is invalid.

    combining G01, G02, G03 commands with either a D01 or D02 cmd
    -------------------------------------------------------------
    this behaviour is deprecated

    it would have looked like:
    G(1|01|2|02|3|03)<Coordinate data>D(01|02)*

    Example:
    G01*
    X100Y100D01*
    G01X500Y500D01*
    X300Y300D01*
    G01X100Y100D01*

    rectangular aperture holes
    --------------------------
    previous versions of this specification also allowed rectangular holes. Rectangular holes are now deprecated.

    they would have looked like:
    <Hole> = <X-axis hole size>X<Y-axis hole size>

    Example:
    %FSLAX26Y26*%
    %MOIN*%
    %ADD10C,10X5X5*%
    %ADD11C,1*%
    G01*
    %LPD*%
    D11*
    X-10000000Y-2500000D02*
    X10000000Y2500000D01*
    D10*
    X0Y0D03*
    M02*

    Deprecated %FS options
    ----------------------
    Trailing Zero suppression (T) is deprecated: %FSTAX25Y25% - the T in this %FS cmd is deprecated
    Only Leading Zero suppression (L) is allowed: %FSLAX25Y25% - the L in this %FS cmd is correct
    If no zeros are suppressed then L should be specified and not D.

    Incremental Coordinate Format (I) is deprecated: %FSLIX25Y25% - the I in this %FS cmd is deprecated
    Only Absolute Coordinate Format (A) is allowed: %FSLAX25Y25% - the A in this %FS cmd is correct

    Using M02 to close an %SR command
    ----------------------------------
    this behavior is deprecated. An empty %SR command should be used close the existing %SR block.

    """

    def __init__(self, grbr_fn: str):
        """Initialize the gerber file's graphic state and normalize the gerber file content.

        :param grbr_fn: The gerber file to be parsed

        Graphic's Initial State:

        Properties with default values:
        * these values can be updated multiple times when parsing the file
            - Current point:  0, 0
            - Step & Repeat:  1, 1, -, -
            - Level polarity: dark
            - Region mode:    off

        The properties must be set before first operation as they do not have default values
        * Can only be set once, and then they cannot be modified:
            - Coordinate format:
            - Unit:
        * Can be set and modified any number of times:
            - Current aperture:
            - Quadrant mode:
            - Interpolation mode:

        File Content/Command Normalization:

        The contents of the gerber file (i.e. the commands) are normalized so that there is only one functional
        command or one extended command per line. Such that all lines will either:

        1) not be enclosed in % characters and end with a *. This line will have only 1 * and it will be the
           last character.
        2) be enclosed in % characters and have an * immediately before the closing % character. It MAY
           contain multiple data-block and hence may contain multiple * characters.

            XXXXXXXXX*      -- this a functional command
            %XXXXXXX*%      -- this is an extended command (enclosed in parens)

        Note that all extended commands, with the exception of the %AM extended command, only have 1 data-block
        and hence will only contain a single * character immediately before the closing % character. However,
        %AM commands will have multiple data-blocks and hence multiple * characters. The logic that handles %AM
        commands will first trim of the enclosing % characters and then break the data blocks into a list by
        splitting the string on the * character.
        """
        self.gcs: GrbrCoordSys | None = None  # the GrbrCoordSys helper object used to parse gerber coordinates
        self.aperture_lkp: dict[
            str, tuple[str, list][str]
        ] = {}  # the aperture dictionary that stores apertures by aperture ID when added (%AD)
        self.macro_lkup: dict[str, Any]  # the dictionary to store aperture macro definitions by macro name
        self.curr_x: float = 0  # the current x coordinate
        self.curr_y: float = 0  # the current y coordinate
        self.region_mode: bool = False  # tracks if we are in a region definition (G36 on /G37 off)
        self.polarity: str = "dark"  # tracks what the current layer's polarity is "dark" or "clear" (a layer can only be either dark or clear and cannot be changed) (%LP)
        self.step_repeat = (1, 1, None, None)  # the settings for the current step repeat operation (%SR)
        self.step_repeat_flag = False  # set to true when we are inside a step and repeat command
        # an empty %SR*% will end and EXECUTE the current step and repeat command
        # a non-empty %SR...*% will end and EXECUTE the current step and repeat command and begin another step and repeat command
        self.aperture: str | None = None  # the current aperture (set by Dnn* where nn >= 10)
        self.interpolation_mode: str | None = (  # the current interpolation mode (G01 linear, G02 CW circular, G03 CCW circular)
            None
        )
        self.quadrant_mode: str | None = None  # the current quadrant mode (G74 single, G75 multi)
        self.comment_hist: list[  # stores a list of all comments in the file in order of occurrence
            tuple[int, str]
        ] = []
        self.attrib_hist = []  # stores a list of all attribute in the file, by TYPE, NAME, order of occurrence
        self.curr_attribs = {  # dictionary to hold the current attributes in effect for each attribute type
            "TF": {},
            "TA": {},
            "TO": {},
        }
        self.grbr_fn = grbr_fn  # file name path of the gerber file to parse
        self.lines: list[str] = self.read_and_normalize_grbr()  # the normalized gerber commands

    def read_and_normalize_grbr(self) -> list[str]:
        # read the gerber file and return a list of strings containing 1 command or extended command per string
        #   note: extended MA commands will contain multiple data blocks
        #
        # step 1 -> grbr_text
        #   1. read file in as a list of strings
        #   2. remove leading & trailing white space from each string
        #   3. convert the list of string to 1 big string
        #
        # step 2 -> norm_grbr_text
        # loop over each character in grbr_text adding newlines as needed
        #   1. at the end of every extended command %xx...*%
        #      note: extended commands containing multiple data blocks (%MA) will be
        #      formatted as 1 line. We will handle splitting these into in separate data blocks
        #      in the function that handles AM extended commands.
        #           am_cmd = "%AMDONUTFIX*1,1,0.100,0,0*1,0,0.080,0,0*%"
        #           dblks = am_cmd[3:-2].split("*")
        #   2. at the end of every function command ...xnn* / xnn*
        #   3. with the following exception: if the function command is the last command in an
        #      extended command, no newline is added
        #
        # step 3 -> norm_grbr_lines
        #   1. join norm_grbr_text back into a big string
        #   2. remove the last newline from the string
        #   3. split the string on newlines back into a list of commands/extended commands

        # step 1
        with open(self.grbr_fn) as gfh:
            grbr_lines = gfh.readlines()
        grbr_text = "".join(map(lambda l: l.strip(), grbr_lines))
        del grbr_lines

        # step 2
        in_extnd_cmd = False
        norm_grbr_text = []
        for char in grbr_text:
            # add a newline
            #   if we are in an extended command and the current char is a '%'
            #   or we are not in an extended command and the current char is a '*'
            # else do not add a newline
            if (in_extnd_cmd and char == "%") or (not in_extnd_cmd and char == "*"):
                norm_grbr_text.append(f"{char}\n")
            else:
                norm_grbr_text.append(char)
            # if the current char is a '%', flip the in_extnd_cmd flag
            if char == "%":
                in_extnd_cmd = not in_extnd_cmd

        # step 3
        return "".join(norm_grbr_text).rstrip("\n").split("\n")

    def parse_coord_fmt(self, ln_nbr: int, line: str):
        """Parse the %FS command and store the specified values in the graphics state.

        :param ln_nbr: line number of the command
        :param line: the gerber command to process

        A coordinate number in a Gerber file is represented by a sequence of digits without any separator
        between integer and decimal parts of the number. The integer and decimal parts are specified by
        their lengths in a coordinate number. The FS command defines the lengths of the integer and decimal
        parts for all coordinate numbers in the file. The unit in which the coordinates are expressed is
        set by the %MO command. A coordinate number must have at least one character. Zero therefore
        must be encoded as “0”.

        parameters for the %FS command
        1. Zero suppression - only L (leading zero suppression) is supported
           T (trailing zero suppression)is deprecated and D (no zero suppression) is invalid acording to the specs
        2. Coordinate Notation - only A (absolute notation) is supported
           I (incremental notation) is deprecated
        3. number of integer and decimal digits for the x coordinate
            number of integer digits must be 0 thru 6
            number of decimal digits must be 4 thru 6
        4. number of integer and decimal digits for the y coordinate (see #3 above).

        the spec says that the same format must be defined for X and Y.

        The number of integer and decimal digits is stored in a helper object: GrbrCoordSys which includes a
        method for parsing coordinates.
        """
        m = re.match(r"^%FSLAX(\d)(\d)Y\d\d\*%$", line)
        int_len, dec_len = int(m.group(1)), int(m.group(2))

        self.gcs = GrbrCoordSys(int_len, dec_len)

        if STATE_DISP:
            print(f"[{ln_nbr:0>3}] SET: coordinate format integer len: {int_len}, decimal len: {dec_len}")

    def parse_units(self, ln_nbr: int, line: str) -> None:
        """Parse the %MO command and store the specified units in the graphics state.

        :param ln_nbr: line number of the command
        :param line: the gerber command to process

        Allowed units:
        - MM - millimeters
        - IN - inches
        """
        m = re.match(r"^%MO(MM|IN)\*%$", line)
        units = m.group(1)

        if units == "MM":
            self.gcs.set_units("mm")
        elif units == "IN":
            self.gcs.set_units("in")
        else:
            raise Exception(f"Unit of measure: {units} not implemented")

        if STATE_DISP:
            print(f"[{ln_nbr:0>3}] SET: mode (units) to {self.gcs.units}")

    def parse_polarity(self, ln_nbr: int, line: str):
        """Parse the %LP command and store the specified polarity in the graphics state.

        :param ln_nbr: line number of the command
        :param line: the gerber command to process

        Allowed polarities:
        - C - clear
        - D - dark
        """
        m = re.match(r"^%(LP[CD])\*%$", line)
        polarity_cmd = m.group(1)

        if polarity_cmd == "LPC":
            self.polarity = "clear"
        elif polarity_cmd == "LPD":
            self.polarity = "dark"
        else:
            raise Exception(f"Level Polarity Command: {polarity_cmd} not implemented")

        if STATE_DISP:
            print(f"[{ln_nbr:0>3}] SET: level layer to {self.polarity} polarity")

    def pase_aperture_def(self, ln_nbr: int, line: str):
        """Parse the %AD command and store the aperture definition in the aperture dictionary.

        :param ln_nbr: line number of the command
        :param line: the gerber command to process

        parameters for the %AD command
        1. Dnn - the aperture id to use to store the aperture definition in the aperture dictionary
        2. standard aperture name (C, R, O, P) or macro aperture name - the name of the aperture to
           use in the aperture definition
        3. modifier set - optional list of `X` delimited modifier values. The modifiers specified
           or required depends on aperture name being used

        The allowed range of aperture ID valuess is from 10 up to 2,147,483,647. The values 0 to 9
        are reserved and cannot be used. Once an aperture id is assigned it cannot be re-assigned,
        thus apertures are uniquely identified by aperture id.

        the modifier set is split on the 'X' character and the results are stored as a list of strings

        dimensions of the modifiers are in the units set by the %MO command and are decimal values
        (not coordinate values whose format is given by the %FS command) as such the %FS command has
        no effect on the dimensions specified as aperture sizes.

        modifiers for standard apertures
        * C: Circle
            - circle diameter - required
            - hole diameter - optional
            - e.g.: %ADD10C,0.5*% %ADD10C,0.5X0.25*%
        * R: Rectangle
            - X - width of the rectangle - required
            - Y - height of the rectangle - required
            - hole diameter - optional
            - e.g.: %ADD22R,0.044X0.025*% %ADD22R,0.044X0.025X0.019*%
        * O: Obround
            - this should be thought of as a slot shape and not an oval or rounded rectangle
            - x and y form a bounded box for the shape
            - the shorter dimension will be the sides that are rounded
            - the radius of the semicircle used to perform the rounding is 0.5 * shortest_dim
            - note that the length of the slot is not measured from center to center but instead from
              end to end.
            - X - width of the enclosing box - required
            - Y - height of the enclosing box - required
            - hole diameter - optional
            - e.g.: %ADD22O,0.046X0.026*% %ADD22O,0.046X0.026X0.019*%
            - the first example specifies (assume units of inches)
                an aperture id of D22
                a standard aperture name of O (capital oh, not zero)
                a width of 0.046 inches
                a height of 0.26 inches
                no hole
                so the rounding will be applied on the left and right sides as the height is shorter than the width
        * P: Regular Polygon
            - The Diameter of the polygon's circumscribed circle (i.e., distance vertex to vertex) - required
            - The Number of vertices the polygon has - a value from 3 to 12 - required
            - The number of Degrees to rotate the polygon around its center. if no value or a value of 0 is
              specified, (at least) one vertex of the polygon will lie on the positive X-axis through the center
              of the polygon. Rotation should be a decimal value; positive value for counterclockwise rotation
              and negative value for clockwise rotation. -- optional
            - hole diameter - optional, if specified, then the degrees of rotation must also be specified. see,
              the 2nd example below which has a 0.0 degrees of rotation and a hole diameter.
            - e.g.: %ADD17P,.040X6*% %ADD17P,.040X6X0.0X0.019*%
        """
        m = re.match(r"^%AD(D\d{2,})([^,]+)(?:,([X.\d]+))?\*%$", line)
        aperture_id, aperture_type, aperture_params_str = m.group(1), m.group(2), m.group(3)

        # split the modifies for the aperture, if there are no modifiers an empty list will be used
        aperture_params = aperture_params_str.split("X") if aperture_params_str else []
        # store the aperture definition as a tuple with the name and modfiers/parameters
        self.aperture_lkp[aperture_id] = (aperture_type, aperture_params)

        if APRTR_ADD_DISP:
            print(f"[{ln_nbr:0>3}] ADD aperture:  {aperture_id:>5} {aperture_type:>11}        {aperture_params}")

    def parse_g_cmd(self, ln_nbr: int, line: str) -> None:
        R"""
        Parse Gnn gerber codes.

        :param ln_nbr: line number of the command
        :param line: the gerber command to process

        With the exception of G04 (comments), all other Gnn codes are expected to be on a line by
        themselves with no additional data, end with an * and have no leading or trailing white spaces.
        Any spaces between the G04 code and the beginning of the comment will be stripped, as will any
        spaces between the last non-space character and the *

        Comments may be 65,535 characters long (excluding the leading G04 code and the trailing *)
        Per the gerber specification, comments cannot start with the characters: #, @, or ! (this is not
            enforced at the moment)
        Per the gerber specification, strings (and comments are strings) cannot contain the characters: % or *
            however, the code does not currently check for % and a * will terminate the line.

        Note: Unicode escape sequences in comments are not supported at this time - 2023/08/05

        Comments support 4 hex digit Unicode escape sequence: \uXXXX
            Unicode escape sequences must have 4 hex digits after the \u
            Unicode escape sequences less than 4 hex digits must be left padded with leading zeros
        Regarding backslash characters. Backslash characters may appear withing strings IF they are not
            followed by a lower case 'u' character followed by 4 characters that could be interpreted as
            hex digits. If this use case applies, you need to use the Unicode escape sequence \u00A9 to
            represent the backslash character.
        """
        m = re.match(r"^(G\d\d)([^*]*)\*$", line)
        g_cmd = m.group(1)

        # ######################################################################
        # enable linear interpolation mode
        # ######################################################################
        if g_cmd == "G01":
            self.interpolation_mode = "linear"
            if STATE_DISP:
                print(f"[{ln_nbr:0>3}] SET: interpolation mode to: linear ")

        # ######################################################################
        # enable clockwise circular interpolation mode
        # ######################################################################
        elif g_cmd == "G02":
            self.interpolation_mode = "clockwise"
            if STATE_DISP:
                print(f"[{ln_nbr:0>3}] SET: interpolation mode to: circular clockwise")

        # ######################################################################
        # enable counterclockwise circular interpolation mode
        # ######################################################################
        elif g_cmd == "G03":
            self.interpolation_mode = "counterclockwise"
            if STATE_DISP:
                print(f"[{ln_nbr:0>3}] SET: interpolation mode to: circular counterclockwise")

        # ######################################################################
        # comment
        # ######################################################################
        elif g_cmd == "G04":
            comment = m.group(2).strip()
            self.comment_hist.append((ln_nbr, comment))
            if COMMENT_DISP:
                print(f"[{ln_nbr:0>3}] COMMENT")

        # ######################################################################
        # region on
        # ######################################################################
        elif g_cmd == "G36":
            self.region_mode = True
            print(f"[{ln_nbr:0>3}] REGION: start")

        # ######################################################################
        # region off
        # ######################################################################
        elif g_cmd == "G37":
            self.region_mode = False
            print(f"[{ln_nbr:0>3}] REGION: end")

        # ######################################################################
        # enable single quadrant mode
        # ######################################################################
        elif g_cmd == "G74":
            self.quadrant_mode = "single"
            if STATE_DISP:
                print(f"[{ln_nbr:0>3}] SET: quadrant mode to: single")

        # ######################################################################
        # enable multi quadrant mode
        # ######################################################################
        elif g_cmd == "G75":
            self.quadrant_mode = "multi"
            if STATE_DISP:
                print(f"[{ln_nbr:0>3}] SET: quadrant mode to: multi")

        # ######################################################################
        # not a command we understand
        # ######################################################################
        else:
            raise Exception(f"Line: {ln_nbr}, G Command: {g_cmd} not implemented")

    def parse_m_cmd(self, ln_nbr: int, line: str):
        """Parse the M command, finish all processing, release open resources and end file parsing.

        :param ln_nbr: line number of the command
        :param line: the gerber command to process

        Only 1 Mnn command is supported and that is the M02 command which signifies the end of the gerber file.
        """
        m = re.match(r"^(M\d\d)\*$", line)
        m_cmd = m.group(1)

        if m_cmd == "M02":
            # TODO: perform any processing needed to occur before exiting
            # TODO: clean up any resources in use/open
            pass
        else:
            raise Exception(f"M Command: {m_cmd} not implemented")

        print(f"[{ln_nbr:0>3}] ### END OF FILE ###")

    def parse_d_cmd(self, ln_nbr: int, line: str) -> None:
        """
        Parse the Dnn gerber code and take the appropriate actions.

        :param ln_nbr: line number of the command
        :param line: the gerber command to process

        Dnn commands include D01 (interpolate), D02 (move), D03 (flash) and Dnn where nn is >= 10. This
        last set of Dnn commands are used to set the current aperture. D02 and D03 take X & Y coordinates
        as their parameters and D01 takes X & Y coordinates as its parameters for all interpolation modes
        as well as I & J offset values for non-linear interpolation modes.

        Aperture IDs:
        The allowed range of aperture ID values is from 10 thru 2,147,483,647. Values 0 thur 9 are
        reserved and cannot be used for aperture IDs. Once an aperture ID is assigned it cannot be
        re-assigned, thus apertures are uniquely identified by their aperture ID.

        When an aperture is created using the %AD command, the aperture definitions (its type [C, R,
        O, P] or an `Aperture Macro Name` defined by an %AM command, and any corresponding parameters)
        are stored in the aperture dictionary using the specified aperture ID.

        When a Dnn set aperture command is encountered, its definition is retrieved by its
        corresponding aperture ID from the aperture dictionary.

        interpolation modes:
        There are 3 interpolation modes:
            * `linear` interpolation mode - set by the G01 cmd
            * circular `clockwise` interpolation mode - set by the G02 cmd
            * circular `counterclockwise` interpolation mode - set by the G03 cmd

        quadrant modes:
        there are 2 quadrant modes:
            * `single` quadrant mode = set by the G74 cmd
            * `multi` quadrant mode = set by the G75 cmd

        When in single` quadrant mode,  the `I` & `J` offset values do NOT have their sign indicated - so
        it must be determined by examining the radius when calculated using the arc's starting point
        (the current x, y coordinates) and the radius when calculated using the arc's ending point
        (the x, y coordinates given in the D01 cmd).

        When in `multi` quadrant mode,  the `I` & `J` offset values DO have their signs indicated, so the
        above determination is not required.

        Coordinate Data:
        The following letters are used to specify the type of coordinate is being provided:
            * `X` & `Y` - Characters indicating X or Y coordinates of a point
            * `I` & `J` - Characters indicating a distance or offset in the X or Y direction. `I` & `J` are
                          only allowed in a D01 command and only when in CW/CCW circular interpolation mode.

        X & Y coordinates are modal, I & J offsets are NOT modal.
            * If an X coord is omitted then the current point's X coord is used. The same applies to the Y coord.
            * If an `I` offset is omitted then 0 is used as the `I` offset. The same applies to the J offset.

        The %FS extended command specifies how to interpret the coordinate values (refer to the `parse_coord_fmt`
        function and the `parse_grbr_coord` method in the GrbrCoordSys class for additional details). And the
        %MO command specifies which units MM (metric millimeters) or IN (empirical inches) are used. Note:
        currently only the LA (leading zeros suppressed and absolute coordinates) format is currently supported.
        T (trailing zero suppression) is deprecated. D (no zero suppression) is invalid. Additionally, only
        `A` (absolute coordinates) are supported. The `I` (incremental coordinates) is deprecated.

        regardless of zero suppression, if a coordinate/offset specifier (X, Y, I, J) is present, the
        corresponding value must also be present. At least 1 digit must be specified, even for a value of
        zero. To omit a given entirely, do not specify any part of it.

        example data for an interpolate line D01 cmd in linear interpolation mode (G01):
            X700Y1000

        example data for an interpolate arc D01 cmd for CW/CCW circular interpolation mode (G02/G03) single
        quadrant mode (G74) where the `I` and `J` coordinate values are unsigned.
            X700Y1000I400J0D01

        example data for an interpolate arc D01 cmd for CW/CCW circular interpolation mode (G02/G03) multi
        quadrant mode (G75) where the `I` and `J` coordinate values are signed (with a `-` or optional `+`).
            X300Y200I-300J-400D
        """
        m = re.match(r"^(?:X(\d*))?(?:Y(\d*))?(?:I(-?\d*))?(?:J(-?\d*))?(D0[123])|(D\d{2,})\*$", line)
        d_cmd = m.group(5)
        aperture_id = m.group(6)

        x = y = delta_x = delta_y = delta_len = off_i = off_j = cx = cy = radius = None

        # ######################################################################
        # calculate the following when processing a D01, D02, D03 cmd, but
        # not for a set current aperture command.
        # ######################################################################
        if d_cmd:
            # all D01, D02, D03 cmds need to have x & y coordinate values
            x = self.gcs.parse_grbr_coord(m.group(1)) if m.group(1) else self.curr_x
            y = self.gcs.parse_grbr_coord(m.group(2)) if m.group(2) else self.curr_y

            # calculate the following only for CW / CCW circular interpolation mode
            if self.interpolation_mode != "linear":
                # parse the i and j offset values from the D01 command
                off_i = self.gcs.parse_grbr_coord(m.group(3)) if m.group(3) else 0
                off_j = self.gcs.parse_grbr_coord(m.group(4)) if m.group(4) else 0

                if self.quadrant_mode == "single":
                    # when in single quadrant mode, we must determine the sign (+/-) of the offset values
                    radius, off_i, off_j = get_signed_offsets(off_i, off_j, x, y, self.curr_x, self.curr_y)
                else:
                    radius = calc_length(off_i, off_j)

                # calculate the arc's center point from the current x, y coordinates adjusted
                # for the arc's center point offset i, j values
                cx, cy = self.curr_x + off_i, self.curr_y + off_j

            # calc delta values for X, Y and len
            delta_x, delta_y = x - self.curr_x, y - self.curr_y
            delta_len = round(calc_length(delta_x, delta_y), 3)

            # only set the current point's x, y coordinates after all the above calculations are completed
            self.curr_x, self.curr_y = x, y

        # ######################################################################
        # MOVE to location
        # ######################################################################
        if d_cmd == "D02":
            # only takes parameters of x & y
            if DRAW_DISP:
                if delta_len:
                    print(
                        f"[{ln_nbr:0>3}] MOVE to:  {x:>10.3f}, {y:>10.3f}  {delta_x:>10.3f}, {delta_y:>10.3f}     len: {delta_len}"
                    )
                else:
                    # if the delta len is 0, then the coordinates that are being moved to, are the same as the current point!
                    print(
                        f"[{ln_nbr:0>3}] MOVE to: #{x:>10.3f}, {y:>10.3f}  {delta_x:>10.3f}, {delta_y:>10.3f}     len: {delta_len} ##############"
                    )

        # ######################################################################
        # INTERPOLATE a line or an arc
        # ######################################################################
        elif d_cmd == "D01":
            # only takes parameters of x & y when interpolation mode is `linear`
            # also takes parameters of i & j when interpolation mode is circular `clockwise` / `counterclockwise`
            if DRAW_DISP:
                if self.interpolation_mode == "linear":
                    print(
                        f"[{ln_nbr:0>3}] LINE to:  {x:>10.3f}, {y:>10.3f}  {delta_x:>10.3f}, {delta_y:>10.3f}     len: {delta_len}    {self.aperture:>10}"
                    )
                else:
                    print(
                        f"[{ln_nbr:0>3}] ARC to:   {x:>10.3f}, {y:>10.3f}  {delta_x:>10.3f}, {delta_y:>10.3f}     len: {delta_len}    {self.aperture:>10}     (offset: {off_i}, {off_j}  center: {cx}, {cy}  radius: {radius})"
                    )

        # ######################################################################
        # FLASH an aperture
        # ######################################################################
        elif d_cmd == "D03":
            # only takes parameters of x & y
            if FLASH_DISP:
                print(
                    f"[{ln_nbr:0>3}] FLASH at: {x:>10.3f}, {y:>10.3f}   {delta_x:>10.3f}, {delta_y:>10.3f}     len: {delta_len}    {self.aperture:>10}"
                )

        # ######################################################################
        # SET current aperture
        # ######################################################################
        elif aperture_id in self.aperture_lkp:
            # setting the current aperture does not take any additional parameters
            # only the aperture ID is required (i.e., Dnn where nn >= 10)
            self.aperture = aperture_id
            if APRTR_SET_DISP:
                print(
                    f"[{ln_nbr:0>3}] SET: current aperture to: {aperture_id} -> "
                    f"{self.aperture_lkp[aperture_id][0]}: {self.aperture_lkp[aperture_id][1]}"
                )

        # ######################################################################
        # not a command we understand
        # ######################################################################
        else:
            raise Exception(f"D Command: {d_cmd} not implemented or not in aperture dictionary")

    def parse_attribute(self, ln_nbr: int, line: str):
        """Parse the all %Tx attribute command and update the appropriate attribute dictionary.

        :param ln_nbr: line number of the command
        :param line: the gerber command to process

        attribute types we've seen so far are:
          TF, TA, TD, TO
          note: TO, which is emitted by KiCad for pads and traces, appears to be non-standard?

        the attribute type is immediately followed by the attribute name. The attribute name is delimited
          by a comma.

        after the comma following the attribute name, is 1 or more comma delimited values
        no spaces or commas are allowed in the name or any of the values

        for TA (aperture) attributes usage in the gerber file, the pattern is to
          - 1st clear desired/all existing aperture attributes (%TD*)
          - 2nd create all aperture attributes that should be attached (%TA...*)
          - 3rd create the aperture. it will have all the aperture attributes that were in existence at
              the time the aperture was created. (%AD)

        for TD, this command was originally used to delete TA attribs
          but, it looks like KiKad is treating it as deleting TO attribs too???
        """

        m = re.match(r"^%(T.)([^,]*),?([^*]*)\*%$", line)
        attrib_type, attrib_name, attrib_value = m.group(1), m.group(2), m.group(3)

        # add the attribute to the attribute history list, which can optionally displayed at the end of the output
        self.attrib_hist.append((attrib_type, attrib_name, ln_nbr, attrib_value))

        # ######################################################################
        # Delete a previous created attribute - (should) only applies to Aperture attributes
        # ######################################################################
        if attrib_type == "TD":
            # when deleting attributes, the name is optional and if not given all attributes are deleted
            if attrib_name:
                self.curr_attribs["TA"].pop(attrib_name, None)
                self.curr_attribs["TO"].pop(attrib_name, None)  # thanks KiCad
            else:
                self.curr_attribs["TA"].clear()
                self.curr_attribs["TO"].clear()  # thanks KiCad

            if ATTRIB_DISP:
                print(f"[{ln_nbr:0>3}] ATTRIB-DEL: name {attrib_name if attrib_name else 'ALL'}")

        # ######################################################################
        # Set an attribute - applies to all
        # ######################################################################
        elif attrib_type in ("TF", "TA", "TO"):
            # when setting a new attrib, there will be at least 1 attrib value after the attrib name, store as a list of str
            attrib_vals = attrib_value.split(",")
            # store the list of values in the appropriate attribute dictionary under the attrib's name
            self.curr_attribs[attrib_type][attrib_name] = attrib_vals

            if ATTRIB_DISP:
                print(f"[{ln_nbr:0>3}] ATTRIB-SET: type {attrib_type}, name {attrib_name}")


def get_args(args_list: list[str] | None = None) -> argparse.Namespace:
    """Get the command line arguments passed in.

    :param args_list: for testing/development only
    :return: the list of arguments passed in

    there is 1 required positional argument, and that is the gerber file name path to be parsed.
    There are a number of option that affect what is output. These options are used to set GLOBAL flag variables.
    """
    global ATTRIB_DISP, COMMENT_DISP, STATE_DISP, APRTR_ADD_DISP, APRTR_SET_DISP, FLASH_DISP, DRAW_DISP, HIST_ATTRIB_DISP, HIST_COMMENT_DISP, ATTRIB_SUM_DISP

    # TODO: ideas for new options
    #   - suppress region content
    #   - suppress move to with zero delta length

    parser = argparse.ArgumentParser(
        prog="Grbr To English",
        description="will explain what each line of a gerber file does",
        epilog="Its better to burn out than fade away...",
    )
    parser.add_argument("grbr_filename", help="The Name of the Gerber File to parse")
    parser.add_argument(
        "-a",
        "--no-aptr",
        action="store_false",
        dest="aprtr_add_disp",
        help="pass --no-aptr to suppress the display of grbr cmds which define an aperture",
    )
    parser.add_argument(
        "-s",
        "--no-state",
        action="store_false",
        dest="state_disp",
        help="pass --no-state to suppress the display of grbr cmds which update the graphics state",
    )
    parser.add_argument(
        "-d",
        "--no-draw",
        action="store_false",
        dest="draw_disp",
        help="pass --no-draw to suppress the display of interpolate & move grbr cmds",
    )
    parser.add_argument(
        "-f",
        "--no-flash",
        action="store_false",
        dest="flash_disp",
        help="pass --no-flash to suppress the display of flash grbr cmds",
    )
    parser.add_argument(
        "-t",
        "--with-attr",
        action="store_true",
        dest="attrib_disp",
        help="pass --with-attr to display grbr cmds which define attributes",
    )
    parser.add_argument(
        "-c", "--with-cmnt", action="store_true", dest="comment_disp", help="pass --with-cmnt to display comments"
    )
    parser.add_argument(
        "-p",
        "--with-aptr",
        action="store_true",
        dest="aprtr_set_disp",
        help="pass --with-aptr to display grbr cmds which set the current aperture",
    )
    parser.add_argument(
        "-S",
        "--attr-sum",
        action="store_true",
        dest="attrib_sum_disp",
        help="pass --attr-sum to display the final attribute state after the file is finished parsing",
    )
    parser.add_argument(
        "-A",
        "--attr-hist",
        action="store_true",
        dest="hist_attrib_disp",
        help="pass --attr-hist to display the commands executed to set/delete attributes",
    )
    parser.add_argument(
        "-C",
        "--cmnt-hist",
        action="store_true",
        dest="hist_comment_disp",
        help="pass --cmnt-hist to display the grbr file comment contents",
    )
    args = parser.parse_args(args_list)

    ATTRIB_DISP = args.attrib_disp
    COMMENT_DISP = args.comment_disp
    STATE_DISP = args.state_disp
    APRTR_ADD_DISP = args.aprtr_add_disp
    APRTR_SET_DISP = args.aprtr_set_disp
    FLASH_DISP = args.flash_disp
    DRAW_DISP = args.draw_disp
    HIST_ATTRIB_DISP = args.hist_attrib_disp
    HIST_COMMENT_DISP = args.hist_comment_disp
    ATTRIB_SUM_DISP = args.attrib_sum_disp

    return args


def main():
    TESTING = False
    # grbr_fn = "/Users/gregskluzacek/Documents/PCB/KiCad/cnc_test/cnc_test-Edge_Cuts.gbr"
    # grbr_fn_f_mask = "/Users/gregskluzacek/Documents/PCB/KiCad/cnc_test/cnc_test-F_Mask.gbr"
    # grbr_fn_f_cu = "/Users/gregskluzacek/Documents/PCB/KiCad/cnc_test/cnc_test-F_Cu.gbr"
    grbr_fn = "/Users/gregskluzacek/Documents/PCB/KiCad/cnc_test/cnc_test-F_Cu.gbr"
    # grbr_fn = "/Users/gregskluzacek/Documents/PCB/KiCad/cnc_test/cnc_test-F_Cu copy.gbr"

    # get the command line arugments passed in
    test_args = None
    if TESTING:
        test_args = [grbr_fn, "-pSAC"] + sys.argv[1:]
    args = get_args(test_args)

    # read gerber file and normalize the commands
    grbr_plot = GrbrPlot(args.grbr_filename)

    print("-" * 100)
    print(f"Explaining gerber file: {os.path.basename(grbr_fn)}")
    print("-" * 100)

    # main loop to process each command in the gerber file
    for ln_nbr, line in enumerate(grbr_plot.lines, 1):
        # process the coordinate format specifier command
        if line.startswith("%FSLAX") and line.endswith("*%"):
            grbr_plot.parse_coord_fmt(ln_nbr, line)

        # process the Units Mode command
        elif line.startswith("%MO") and line.endswith("*%"):
            grbr_plot.parse_units(ln_nbr, line)

        # process the set Layer Polarity command
        elif line.startswith("%LP") and line.endswith("*%"):
            grbr_plot.parse_polarity(ln_nbr, line)

        # process the Aperture Definition command
        elif line.startswith("%ADD") and line.endswith("*%"):
            grbr_plot.pase_aperture_def(ln_nbr, line)

        # process the Macro Aperture command
        elif line.startswith("%AM") and line.endswith("*%"):
            print(f"[{ln_nbr:0>3}] ------ APERTURE MACRO COMMAND ------")
            process_macro(line)

        # process the Step and Repeat command
        elif line.startswith("%SR") and line.endswith("*%"):
            # TODO: process step and repeat commands
            """
            Example:
            %SRX3Y2I5.0J4.0*%
            G04 Block accumulation started. All the graphics*
            G04 objects created below added to the block*
            ...
            G04 Block accumulation is about to finish*
            %SR*%
            G04 The block is finished and replicated*
            """
            pass

        # process any of the Create Attribute commands or Attribute Delete command
        elif line[0:3] in ("%TF", "%TA", "%TD", "%TO") and line.endswith("*%"):
            grbr_plot.parse_attribute(ln_nbr, line)

        # process any of the Gnn commands
        elif line.startswith("G") and line.endswith("*"):
            grbr_plot.parse_g_cmd(ln_nbr, line)

        # process the End-Of-File command
        elif line.startswith("M") and line.endswith("*"):
            grbr_plot.parse_m_cmd(ln_nbr, line)

        # process any of the Dnn commands
        elif line[0] in ("D", "X", "Y", "I", "J") and line.endswith("*"):
            grbr_plot.parse_d_cmd(ln_nbr, line)

        # handel invalid gerber command
        else:
            output_bad_grbr(ln_nbr, line)

    # output various summaries
    output_attrib_hist(grbr_plot)
    output_comment_hist(grbr_plot)
    output_final_attrib_state(grbr_plot)


def output_bad_grbr(ln_nbr: int, line: str) -> None:
    """Prints out a warning message when an unsupported gerber code is encountered, then continues.

    :param ln_nbr: line number of the command
    :param line: the gerber command to process
    """
    print("")
    print("* " * 50)
    print(f"[{ln_nbr:0>3}] WARNING UNEXPECTED GERBER CODE: {line}")
    print("* " * 50)
    print("")


def output_attrib_hist(grbr_plot: GrbrPlot) -> None:
    """After parsing, prints out all attribute commands encountered during parsing.

    :param grbr_plot:
    :return:

    The history includes all attribute commands including: set/create & delete. The output is first broken out by
    attribute Type (TA, TD, TF, TO). Then within each type, the output is ordered by attribute name and Line Number
    """
    if not HIST_ATTRIB_DISP:
        return

    print("")
    print("- " * 50)
    print("attribute history")

    # sort the attribute history by: attribute Type, attribute name, Line Number
    grbr_plot.attrib_hist.sort()

    for attribute in grbr_plot.attrib_hist:
        # handle attrib hist for non-attrib-delete commands first
        if attribute[0] != "TD":
            print(f"\tline: {attribute[2]}, type: {attribute[0]}, name: {attribute[1]}, values: {attribute[3]}")
        # handle attrib-delete commands deleting a specific attribute name
        elif attribute[1]:
            print(f"\tline: {attribute[2]}, type: {attribute[0]}, name: {attribute[1]}")
        # handle attrib-delete commands deleting  all attributes
        else:
            print(f"\tline: {attribute[2]}, type: {attribute[0]}, name: ALL")


def output_comment_hist(grbr_plot: GrbrPlot) -> None:
    """After parsing, prints out all comments in line number order.

    :param grbr_plot:  GrbrPlot object to use to access the comment history list
    :return:
    """
    if not HIST_COMMENT_DISP:
        return

    print("")
    print("- " * 50)
    print("comment history")
    grbr_plot.comment_hist.sort()
    for comment in grbr_plot.comment_hist:
        print(f"\tline: {comment[0]}, text: {comment[1]}")


def output_final_attrib_state(grbr_plot: GrbrPlot) -> None:
    """After parsing, prints the final entries found in each of the Attribute dictionaries.

    :param grbr_plot: GrbrPlot object to use to access the attribute dictionary
    :return:

    Each of the dictionaries is printed separately ordered by the attribute names
    """
    if not ATTRIB_SUM_DISP:
        return

    print("")
    print("- " * 50)
    print("Attribute Dictionary - File")
    for k, v in sorted(grbr_plot.curr_attribs["TF"].items()):
        print(f"\t{k}: {v}")

    print("")
    print("- " * 50)
    print("Attribute Dictionary - Aperture")
    for k, v in sorted(grbr_plot.curr_attribs["TA"].items()):
        print(f"\t{k}: {v}")

    print("")
    print("- " * 50)
    print("Attribute Dictionary - Nets")
    for k, v in sorted(grbr_plot.curr_attribs["TO"].items()):
        print(f"\t{k}: {v}")


def get_signed_offsets(c_xo: float, c_yo: float, pe_x: float, pe_y: float, ps_x: float, ps_y: float):
    """From an Arc's staring point, ending point, and center offset, calculate its radius and signed offset

    :param c_xo: the UNSIGNED x offset from the arc's starting point to the center point
    :param c_yo: the UNSIGNED y offset from the arc's starting point to the center point
    :param pe_x: the arc's x ending point coordinate
    :param pe_y: the arc's y ending point coordinate
    :param ps_x: the arc's x starting point coordinate
    :param ps_y: the arc's y starting point coordinate
    :return: the radius of the arc, and the signed values of the x & y center offsets

    This function is called when a interpolation (D01) operation is encountered in either CW (G2) or CCW (G3)
    interpolation mode and the graphics state is in single quadrant mode (G74). In this case, the x & y
    center offset values are not signed (as opposed to multi quadrant mode (G75). Therefore we need to
    determine if x should be x or -x and if y should be y or -y.

    To do this, we essentially take each of the 4 candidate center points [(x, y), (-x, y), (-x, -y), (x, -y)] and
    use it in conjunction with the arc's starting and ending points to calculate the respective radius's. The
    candidate center points whose radii are the closest (were dealing with floats and rounding errors, so
    we cannot be exact), is chosen as the actual singed offset.

    detailed description of the process to determine the sign of the x, y center point offsets:

    * calculate the actual radius --> radius
        - to do this, use the center point offsets (c_xo, c_yo) and calculate its distance from the origin
    * calculate the difference between (aka length) the x & y component of the arc's starting
      point (ps_x, ps_y) and the arc's ending point (pe_x, pe_y) --> peo_x, peo_y
        - the distance between the 2 points is a straight line, and we want to know what to know the
          difference between (aka length) the 2 X components and the 2 Y components (aka offset)
    * generate the list of candidate center points offsets as a list --> cco_pts
        - we use a list of points (cq_mvs) represented as positive and negative 1's to multiply the center
          offset (c_xo, c_yo) by
        - the list is order by the 4 quadrants of the cartesian plane
            - index 0: quadrant 1: both x & y are positive (1, 1)
            - index 1: quadrant 2: x is negative and y is positive (-1, 1)
            - index 2: quadrant 3: both x & y are negative (-1, -1)
            - index 3: quadrant 4: x is positive and y is negative (1, -1)
    * for each center point offset candidate (cco_x, cco_y)
        - calculate the difference between (aka length) the x & y components of the arc's starting
          point offset (peo_x, peo_y) and center point offset candidate offset (cco_x, cco_y) --> ccro_x, ccro_y
        - calc the radius using the center point offset candidate (ccro_x, ccro_y) --> cco_radius
        - take the difference between the calculated radius (cco_radius) for the given center point candidate
          offsets and the actual radius (radius) --> diff
        - append this difference (diff) and the index (cq_index) to the corresponding quadrant the the list of
          differences --> diffs
    * multiple the center point offset passed in (c_xo, c_yo) by the multiply value list (cq_mvs)
        - sort the list of differences (diffs) by their tuple values - this will order the list with the center
          point candidate with the smallest difference first and the largest difference last.
        - get the first item in the sorted list
        - use its quadrant index (cq_index) to get the quadrant's x & y multipliers --> xso, yso
        - multiple c_xo, c_yo by xso, yso. this is the signed values of the center point offset
    """
    # data structure to hold the differences between 2 radii and a corresponding cartesian quadrant index
    Diff = namedtuple("Diff", ["rad_diff", "cq_index"])

    # step  1 - calc the radius by taking the length of the center offset vector: c_xo, c_yo
    radius = calc_length(c_xo, c_yo)

    # step 2 - calculate the offset from the arc's starting point to its ending point
    peo_x, peo_y = calc_offset(pe_x, pe_y, ps_x, ps_y)

    # step 3 - build the list of candidate center point as a list by
    # multiply each cartesian quadrant x, y multiplier value with the center points offset's x, y value
    cq_mvs = [(1, 1), (-1, 1), (-1, -1), (1, -1)]
    cco_pts = [(c_xo * mv_x, c_yo * mv_y) for mv_x, mv_y in cq_mvs]

    # step 4 - for each candidate center offset, calculate:
    # 1. the distance between the ending point offset and the candidate center offset (length)
    # 2. the resulting radius length
    # 3. the difference to the actual radius
    diffs = []
    cq_index: int
    for cq_index, (cco_x, cco_y) in enumerate(cco_pts):
        ccro_x, ccro_y = calc_offset(peo_x, peo_y, cco_x, cco_y)
        cco_radius = calc_length(ccro_x, ccro_y)
        diff = Diff(rad_diff=abs(radius - cco_radius), cq_index=cq_index)
        diffs.append(diff)

    # step 5 - sort the results by smallest difference to largest, take the index of the smallest difference
    # and use it to look up the corresponding x & y multiplication values
    smallest_diff = sorted(diffs)[0]
    xso, yso = cq_mvs[smallest_diff.cq_index]

    return radius, c_xo * xso, c_yo * yso


def get_signed_offsets_with_rotation(c_xo: float, c_yo: float, pe_x: float, pe_y: float, ps_x: float, ps_y: float):
    """From an Arc's staring point, ending point, and center offset, calculate its radius and signed offset

    :param c_xo: the UNSIGNED x offset from the arc's starting point to the center point
    :param c_yo: the UNSIGNED y offset from the arc's starting point to the center point
    :param pe_x: the arc's x ending point coordinate
    :param pe_y: the arc's y ending point coordinate
    :param ps_x: the arc's x starting point coordinate
    :param ps_y: the arc's y starting point coordinate
    :return: the radius of the arc, and the signed values of the x & y center offsets

    This function is called when a interpolation (D01) operation is encountered in either CW (G2) or CCW (G3)
    interpolation mode and the graphics state is in single quadrant mode (G74). In this case, the x & y
    center offset values are not signed (as opposed to multi quadrant mode (G75). Therefore we need to
    determine if x should be x or -x and if y should be y or -y.

    To do this, we essentially take each of the 4 candidate center points [(x, y), (-x, y), (-x, -y), (x, -y)] and
    use it in conjunction with the arc's starting and ending points to calculate the respective radius's. The
    candidate center points who's radius's are the closest (were dealing with floats and rounding errors, so
    we cannot be exact), is chosen as the actual singed offset.

    detailed description of the process to determine the sign of the x, y center point offsets:

    For the purposes of this function, a vector is defined as a line starting from the origin (0, 0) to a
    given point (x, y). A vector can represent an offset (magnitude). A vector can also represent an angle
    (direction). The vector's length can be calculated by taking the square root of the sum of the squares
    of its x & y components.

    * calculate the actual radius
        - to do this, use the center point offsets (c_xo, c_yo) and calculate its distance from the origin
    * translate (slide) the arc to the origin
        - to do this use the arc's staring point (ps_x, ps_y) as a vector and subtract it from the starting and ending
          points (i.e. calc the offset).
        - the starting point moves to the origin (0, 0)
        - the ending point moves to: (pe_x - ps_x), (pe_y - ps_y) --> pet_x, pet_y
    * generate the vector (pr_x, pr_y) that will be used to perform the necessary rotation calculations
        - do this by taking the translated end point (pet_x, pet_y) and swap its x, y coordinates --> pr_x, pr_y
    * rotate the translated arc
        - the arc's starting point (pe_x, pe_y) will remain at the origin
        - the arc's translated ending point can be rotated by taking the dot product of: the translated end
          point (pet_x, pet_y) and the rotation vector (pr_x, pr_y) --> per_x, per_y
    * generate the list of candidate center points (cc_pts) as a list of vectors
        - we use a list of points (cq_mvs) represented as positive and negative 1 to multiply the center
          offset (c_xo, c_yo) by
        - the list is order by the 4 quadrants of the cartesian plane
            - index 0: quadrant 1: both x & y are positive (1, 1)
            - index 1: quadrant 2: x is negative and y is positive (-1, 1)
            - index 2: quadrant 3: both x & y are negative (-1, -1)
            - index 3: quadrant 4: x is positive and y is negative (1, -1)
    * for each center point candidate (cc_x, cc_y)
        - rotate it using the rotation vector (pr_x, pr_y) --> ccr_x, ccr_y
        - calc the radius using the candidate center rotated point (ccr_x, ccr_y) and the rotated-translated end
          point (per_x, per_y) --> cc_radius
        - take the difference between the calculated radius (cc_radius) for the given center point candidate
          and the actual radius (radius) --> diff
        - append this difference (diff) and the index (cq_index) to the corresponding quadrant the the list of
          differences --> diff
    * multiple the center point offset passed in (c_xo, c_yo) by the multiply value vectory list (cq_mvs)
        - sort the list of differences (diff) by their tuple values - this will order the list with the center
          point candidate with the smallest difference first and the largest difference last.
        - get the first item in the sorted list
        - use its quadrant index (cq_index) to get the quadrant's x & y multipliers --> xso, yso
        - multiple c_xo, c_yo by xso, mvv. this is the signed values of the center point offset
    """
    # data structure to hold the differences between 2 radii and a corresponding cartesian quadrant index
    Diff = namedtuple("Diff", ["rad_diff", "cq_index"])

    # step 1 - calc the radius by taking the length of the center offset vector: c_xo, c_yo
    radius = calc_length(c_xo, c_yo)

    # step 2 - translate (i.e. slide) ps to the origin & adjust pe by calculating the offsets from
    # ps to pe --> vector: pet_x, pet_y
    pet_x, pet_y = calc_offset(pe_x, pe_y, ps_x, ps_y)
    # print("translated pe:", pet_x, pet_y)

    # step 3 - generate the rotational vector by inverting the transformed pe vector: pet_x, pet_y
    pr_x, pr_y = pet_y, pet_x
    # print("---------------------------------")
    # print("inverted pe:", pr_x, pr_y)

    # step 4 - rotate the translated ending offset vector: pet_x, pet_y
    per_x, per_y = rotate_coords(pet_x, pet_y, pr_x, pr_y)
    # TODO: for an arc wholly contained in the 2nd quadrant, it appears that the rotation occurred in the wrong
    #  direction ??? that is, the sign of the y (per_y) value was flipped, it should have been a negative value,
    #  but it was calculated with a positive value. This may be ok, as offset and other rotations are  flipped too.
    # per_y *= -1
    # print("rotated-translated pe", per_x, per_y)
    # print("---------------------------------")

    # step 5 - build the list of candidate center point as a list of vectors
    # multiply each cartesian quadrant x, y multiplier value with the candidate center point's x, y
    cq_mvs = [(1, 1), (-1, 1), (-1, -1), (1, -1)]
    cc_pts = [(c_xo * mv_x, c_yo * mv_y) for mv_x, mv_y in cq_mvs]

    # step 6 - for each candidate center vectors, calculate:
    # 1. its rotated vector, 2. its resulting radius length and 3. its difference to the actual radius
    diffs = []
    cq_index: int
    for cq_index, (cc_x, cc_y) in enumerate(cc_pts):
        # calculate the rotated vector for the center point candidate
        ccr_x, ccr_y = rotate_coords(cc_x, cc_y, pr_x, pr_y)

        # calc the distance between the rotated vector and the rotated end point (i.e. the radius for the center
        # candidate and end point) by first getting the offset of the x & y components and then getting the
        # length of this offset
        ccr_xo, ccr_yo = calc_offset(ccr_x, ccr_y, per_x, per_y)
        cc_radius = calc_length(ccr_xo, ccr_yo)

        # calculate the difference between length of the radius's
        # then collect the difference and the corresponding index for the current center candidate
        diff = abs(radius - cc_radius)
        diffs.append(Diff(diff, cq_index))
        # print(cq_index, cc_x, cc_y, ccr_x, ccr_y, ccr_xo, ccr_yo, cc_radius, diff)

    # step 7 - sort the results by smallest difference to largest, take the index of the smallest difference
    # and use it to look up the corresponding x & y multiplication values
    smallest_diff = sorted(diffs)[0]
    xso, yso = cq_mvs[smallest_diff.cq_index]

    return radius, c_xo * xso, c_yo * yso


def calc_offset(x1: float, y1: float, x2: float, y2: float) -> tuple[float, float]:
    """Returns the x & y offset between 2 points.

    :param x1: x coordinate of the first point
    :param y1: y coordinate of the first point
    :param x2: x coordinate of the second point
    :param y2: Y coordinate of the second point
    :return: a tuple containing 2 floats: the difference between the x coords & the difference between the y coords

    calculates the `offset` aka the `difference` between 2 points, this can also be thought of the distance
    between the x component of 2 points and the distance between the y components of 2 points
    """
    return x1 - x2, y1 - y2


def calc_length(x: float, y: float) -> float:
    """Returns the length from the origin for a given point.

    :param x: the x coordinate of the point
    :param y: the y coordinate of the point
    :return: the distance between the origin and the given point, i.e., its length

    the function uses the pythagorean theorem to calculate the length of the hypotenuse given a right triangle
    with legs of length X and length Y.
    """
    # TODO: do we need to round?
    # return round((x * x + y * y) ** 0.5, 6)
    return (x * x + y * y) ** 0.5


def rotate_coords(x1: float, y1: float, x2: float, y2: float) -> tuple[float, float]:
    """Calculates and returns the given point p1 (x1, y1) rotated by vector (x2, y2).

    :param x1: X coordinate of the point (p1) to be rotated
    :param y1: Y coordinate of the point (p1) to be rotated
    :param x2: X coordinate of the point (p2) used to perform the rotation
    :param y2: Y coordinate of the point (p2) used to perform the rotation
    :return: the X & Y coordinates for the rotated point (p3)

    the assumption here is that points p1 and p2 are given relative to the origin (i.e., 0, 0)

    the logic below uses the dot product of two vectors to perform the rotation
    This should be faster than using the equivalent trigonometry functions sin() and cos()
    refer to: https://academo.org/demos/rotation-about-point/
    that is:
    x3 = x1*cos(a) - y1*sin(a)
    y3 = y1*cos(a) + x1*sin(a)

    the 2 sets of formulas are equivalent...
    * where cos is defined as the opposite divided by the hypotenuse
    * and sin is defined as the adjacent divided by the hypotenuse
    * then the hypotenuse is equal to the length of point p2 from the origin
    * and the adjacent side is equal to the x2 coordinate
    * and the opposite side is equal to the y2 coordinate
    """
    p2_len = calc_length(x2, y2)
    # TODO: do we need to round?
    # x3 = round((x1 * x2 / p2_len) - (y1 * y2 / p2_len), 6)
    # y3 = round((x1 * y2 / p2_len) + (y * x2 / p2_len), 6)
    x3 = (x1 * x2 / p2_len) - (y1 * y2 / p2_len)
    y3 = (x1 * y2 / p2_len) + (y1 * x2 / p2_len)
    return x3, y3


"""
<AM command> =              AM <Aperture macro name> * <Macro content>
<Macro content> =           {{ <Variable definition> * } { <Primitive> * }}
<Variable definition> =     $K = <Arithmetic expression>
<Primitive> =               <Primitive code>, <Modifier> {, <Modifier> } | <Comment>
<Modifier> =                $M | < Arithmetic expression>
<Comment> =                 0 <Text>

Non-Primitives codes
====================
$ - variable assignment
0 - comment

Primitive codes
===============
 1 - circle
 4 - outline
 5 - polygon
 6 - moiré
 7 - thermal
20 - vector line
21 - center line
"""


primitives_lkp = {
    "1": "CIRCLE",
    "4": "OUTLINE",
    "5": "POLYGON",
    "6": "MORIE",
    "7": "THERMAL",
    "20": "VECTOR-LINE",
    "21": "CENTER-LINE",
}


def process_macro(macro_command: str) -> None:
    """Processes one aperture macro command %MA...*%.

    :param macro_command: the aperture macro command to process. All datablocks must be on the
            same line (i.e., no newlines characters between datablocks)

    * we first split the command string into the macro's name and the macro's datablocks
        - returned datablocks will not end with an `*`
        - the macro is made up of one or more primitive datablocks and may contain multiple
          variable datablocks or comment datablocks
    * we iterate over each datablocks
        - we determine if the datablock is a Variable, Comment or Primitive
        - if a primitive, we split the datablock into its primitive code and its modifier set
        - we then determine the type of primitive it is by examining its code and call the
          corresponding funtion to process it.
    """
    # get the macro name (1st datablock), primitives and any variables/comments (from the remaining datablocks)
    macro_name, datablocks = split_macro_into_datablocks(macro_command)
    print(f"[01]  macro name: {macro_name}")
    print("-" * 100)

    # process the primitives and any variables/comments
    datablock: str
    for dblck_nbr, datablock in enumerate(datablocks, 2):
        # ######################################################################
        # the datablock is a VARIABLE assignment
        # ######################################################################
        if datablock.startswith("$"):
            process_variable(dblck_nbr, datablock)

        # ######################################################################
        # the datablock is a COMMENT
        # ######################################################################
        elif datablock.startswith("0"):
            process_comment(dblck_nbr, datablock)

        # ######################################################################
        # the datablock is a primitive
        # ######################################################################
        else:
            # get the numeric primitive code and the list of modifiers.
            # modifiers can be: 1) a float value, 2) a variable or 3) an expression
            p_code, p_mods = split_primitive_datablock(dblck_nbr, datablock)

            # ######################################################################
            # the primitive is a CIRCLE
            # ######################################################################
            if p_code == "1":
                process_circle_primitive(*p_mods)

            # ######################################################################
            # the primitive is a OUTLINE
            # ######################################################################
            elif p_code == "4":
                # outline
                process_outline_primitive(*get_outline_modifiers(p_mods))

            # ######################################################################
            # the primitive is a POLYGON
            # ######################################################################
            elif p_code == "5":
                # Polygon
                process_polygon_primitive(*p_mods)

            # ######################################################################
            # the primitive is a MOIRE
            # ######################################################################
            elif p_code == "6":
                # moire
                process_moire_primitive(*p_mods)

            # ######################################################################
            # the primitive is a THERMAL
            # ######################################################################
            elif p_code == "7":
                # thermal
                process_thermal_primitive(*p_mods)

            # ######################################################################
            # the primitive is a VECTOR-LINE
            # ######################################################################
            elif p_code == "20":
                # vector line
                process_vector_line_primitive(*p_mods)

            # ######################################################################
            # the primitive is a CENTER-LINE
            # ######################################################################
            elif p_code == "21":
                # center line
                process_center_line_primitive(*p_mods)

            # ######################################################################
            # the primitive code is not valid
            # ######################################################################
            else:
                print(f"#### unexpected primitive code: {p_code}, modifiers: {p_mods} ####")


def chunk_points(coords: Iterable[str]) -> Iterator[tuple[str, str]]:
    """Breaks a list of floats into list of points (of floats).

    :param coords:
    :return:
    """
    iter_coords = iter(coords)

    def make_points_from_list() -> tuple[str, str]:
        """returns a point as a pair of floats from the iter_coords Iterator.

        :return:

        The function makes use of a closure so that function can know how many items were previously consumed
        """
        nonlocal iter_coords
        return next(iter_coords), next(iter_coords)

    # iter will call make_points_from_list until the sentinel value is returned
    return iter(make_points_from_list, False)


def split_macro_into_datablocks(macro_command: str) -> tuple[str, list[str]]:
    """Return the aperture macro's name and its datablocks.

    :param macro_command: aperture macro command string to be split
    :return:

    Note: trailing `*` are stripped from the datablocks by the split operation
    """
    # split %AM...*% command into individual data-blocks (values will not end with * after split)
    # slice off the leading `%` and trailing `*%` characters and split on the `*` character
    macro_lines = macro_command[1:-2].split("*")

    # get the macro name from 1st data-block
    macro_name = macro_lines[0]

    # get the remaining data-blocks to process 1 by 1
    datablocks = macro_lines[1:]

    return macro_name, datablocks


def process_variable(dblck_nbr: int, datablock: str) -> None:
    """output the details of a variable definition

    :param dblck_nbr: integer representing the datablock's sequential order in the aperture macro
    :param datablock: the datablock containing the variable definition's name & value
    """
    m = re.match(r"^(\$\d+)=(.*)$", datablock)
    var_name = m.group(1)
    var_value = m.group(2)
    print(f"[{dblck_nbr:0>2}]  SET Variable:    {var_name}     to: {var_value}")


def process_comment(dblck_nbr: int, datablock: str) -> None:
    """Output the details of a comment

    :param dblck_nbr: integer representing the datablock's sequential order in the aperture macro
    :param datablock: the datablock containing the comment text

    COMMENT: 0
    --------------------------
    The comment primitive has no image meaning. It is used to include human-readable comments into the AM command.
    The comment primitive starts with the ‘0’ code followed by a space and then a single-line text string. The
    text string follows the syntax rules for comments as described in section 3.1.
    """
    # remove the leading `0` character that indicates that the datablock is a comment and strip leading/trailing spaces
    comment = datablock[1:].strip()
    print(f"[{dblck_nbr:0>2}]  COMMENT:         {comment}")


def split_primitive_datablock(dblck_nbr: int, datablock: str) -> tuple[str, list[str]]:
    """Return the primitive code and it's modifier set.

    :param dblck_nbr: integer representing the datablock's sequential order in the aperture macro
    :param datablock: the datablock to be split
    :return:

    Note: leading/trailing white space is removed from each modifier.
    """
    # split the datablock into a list of tokens, then trim leading/trailing spaces from the tokens
    p_tokens = datablock.split(",")
    p_tokens = list(map(lambda s: s.strip(), p_tokens))

    # the primitive code will be the first token
    p_code: str = p_tokens[0]

    # the remaining tokens are the primitive's modifier set
    # modifiers can be: 1) a float value, 2) a variable or 3) an expression
    p_mods: list[str] = p_tokens[1:]

    primitive = primitives_lkp.get(p_code, f"unknown-{p_code}-{len(p_mods)}")
    print(f"[{dblck_nbr:0>2}]  --- PRIMITIVE: {primitive} ----------------")

    return p_code, p_mods


# def get_circle_modifiers(p_mods: list[str]) -> list[str]:
#     """Adds the optional rotation modifier to the Circle's modifier set if it is missing.
#
#     :param p_mods:  list of the circle's modifiers
#     :return:        updated circle modifiers - adds 0 rotation modifier if missing
#     """
#     return [*p_mods, "0"][:5]


def process_circle_primitive(
    exposure: str,
    diameter: str,
    x: str,
    y: str,
    rotation: str = "0",
) -> None:
    """Output the details of a circle primitive.

    :param exposure:        1 for on/dark - will produce an image, 0 for off/clear - will remove an image
    :param diameter:        the diameter of the circle primitive
    :param x:               the x center coordinate of the circle primitive
    :param y:               the y center coordinate of the circle primitive
    :param rotation:        number of degrees to rotate the circle primitive

    CIRCLE: 1
    --------------------------
    1,E,D,X,Y,R

    1. Exposure
    2. Diameter
    3. X coordinate of the center of the circle
    4. Y coordinate of the center of the circle
    5. Rotation (is optional, but recommended to always specify it)

    %AMCIRCLE*1,1,1.5,0,0,0*%

    """
    # added an additional "0" string item to p_mods to handle the optional rotation being omitted
    print(f"\texposure: {'on' if exposure == '1' else 'off'}")
    print(f"\tdiameter: {diameter}")
    print(f"\tcenter point: {x}, {y}")
    print(f"\trotation: {rotation} degrees")


def get_outline_modifiers(p_mods: list[str]) -> list[str]:
    """Reorders the Outline's modifiers so the variable number of x, y values come last, after the rotation modifier.

    :param p_mods: outline modifiers in their original order
        Exp, Vcnt, Sx, Sy, Pi1x, Pi1y, ... Pinx, Piny, Rot
    :return: modifiers with the variable data at the end
        Exp, Vcnt, Sx, Sy, Rot, Pi1x, Pi1y, ... Pinx, Piny

    the modifiers need to be reordered so
    1. that the variable number of x, y values can be collected using *args (and *args is not allowed in the middle
       of a function definition's parameter list
    2. and so we can use named positional parameters in the process_outline_primitive funtion, but pass *params
       when the function is called by the process_macro function
    """
    return [*p_mods[:4], p_mods[-1], *p_mods[4:-1]]


def process_outline_primitive(
    exposure: str,
    point_cnt: str,
    x: str,
    y: str,
    rotation: str,
    *rem_coords: str,
) -> None:
    """Output the details of an outline primitive.

    :param exposure:        1 for on/dark - will produce an image, 0 for off/clear - will remove an image
    :param point_cnt:       excluding the starting point, the number of points (x, y pairs) specified
    :param x:               the x coordinate of the starting point of the outline primitive
    :param y:               the y coordinate of the starting point of the outline primitive
    :param rotation:        number of degrees to rotate the outline primitive
    :param rem_coords:      the x, y coordinates that make up the remaining points of the outline primitive

    OUTLINE: 4
    --------------------------
    An outline primitive is an area enclosed by an n-point polygon defined by its start point and n subsequent
    points. The outline must be closed, i.e. the last point must be equal to the start point. There must be at
    least one subsequent point (to close the outline). The outline of the primitive is actually the contour
    (see 2.6) that consists of linear segments only, so it must conform to all the requirements described for contours.

    4,E,V,X0,Y0,X1,Y1...,Xn,Yn,R

    1. Exposure
    2. Number of Vertices (there is 1 more pt than the number of vertices as you have to explicitly close the outline)
    3. X coordinate of the start of the outline
    4. Y coordinate of the start of the outline
    i. X coordinate of the next point in the outline
    j. Y coordinate of the next point in the outline
    x. X coordinate of the end of the outline (the starting point must be equal to the ending point)
    y. Y coordinate of the end of the outline (the starting point must be equal to the ending point)
    z. Rotation

    %AMOUTLINE*4,1,4,0.1,0.1,0.5,0.1,0.5,0.5,0.1,0.5,0.1,0.1,0*%
    """
    print(f"\texposure: {'on' if exposure == '1' else 'off'}")
    print(f"\trotation: {rotation} degrees")
    print(f"\tstarting point: {x}, {y}")
    print(f"\tpoint count (less the starting point): {point_cnt}")

    # get an iterator of points made from the remaining coordinates and print them out
    points = chunk_points(rem_coords)
    for pt_nbr, (x, y) in enumerate(points, 1):
        print(f"\t[{pt_nbr:0>2}] point: {x}, {y}")


def process_polygon_primitive(
    exposure: str,
    vertices: str,
    x: str,
    y: str,
    diameter: str,
    rotation: str,
) -> None:
    """Output the details of a polygon primitive.

    :param exposure:        1 for on/dark - will produce an image, 0 for off/clear - will remove an image
    :param vertices:        the Number of Vertices (between 3 and 12) of the polygon primitive
    :param diameter:        the diameter of the circumscribed circle of the polygon primitive
    :param x:               the x center coordinate of the polygon primitive
    :param y:               the y center coordinate of the polygon primitive
    :param rotation:        number of degrees to rotate the polygon primitive

    POLYGON: 5
    --------------------------
    A polygon primitive is a regular polygon defined by the number of vertices n, the center point and the
    diameter of the circumscribed circle. The first vertex is on the positive X-axis through the center point.

    5,E,V,X,Y,D,R

    1. Exposure
    2. Number of Vertices (between 3 and 12)
    3. X coordinate of the center of the Polygon
    4. Y coordinate of the center of the Polygon
    5. Diameter of the circumscribed circle
    6. Rotation (only allowed when the center point coincides with the origin)

    %AMPOLYGON*5,1,8,0,0,8,0*%
    """
    print(f"\texposure: {'on' if exposure == '1' else 'off'}")
    print(f"\tdiameter: {diameter}")
    print(f"\tcenter point: {x}, {y}")
    print(f"\tnuber of vertices: {vertices}")
    print(f"\trotation: {rotation} degrees")


def process_moire_primitive(
    x: str,
    y: str,
    outer_dia: str,
    ring_thick: str,
    gap_thick: str,
    max_rings: str,
    crshr_thick: str,
    crshr_len: str,
    rotation: str,
) -> None:
    """Output the details of a moiré primitive.

    :param x:               the x center coordinate of the moiré primitive
    :param y:               the y center coordinate of the moiré primitive
    :param outer_dia:       the outer diameter of the outermost concentric ring of the moiré primitive
    :param ring_thick:      the ring thickness of all rings of the moiré primitive
    :param gap_thick:       the distance between the concentric rings of the moiré primitive
    :param max_rings:       the maximum number of rings of the moiré primitive
    :param crshr_thick:     the thickness of the line used to draw the crosshair the moiré primitive
    :param crshr_len:       the height/width of the crosshair of the moiré primitive
    :param rotation:        number of degrees to rotate the moiré primitive

    MOIRÉ: 6
    --------------------------
    The moiré primitive is a cross-hair centered on concentric rings (annuli). Exposure is always on

    6,X,Y,OD,RT,RG,RM,CT,CL,R

    1. X coordinate of the center of the Moiré
    2. Y coordinate of the center of the Moiré
    3. Outer Diameter of the outermost concentric ring
    4. Ring Thickness of all rings
    5. Ring Gap - the distance between the concentric rings
    6. Ring Maximum - the maximum number of rings
    7. Crosshair Thickness - the thickness of the line used to draw the crosshair
    8. Crosshair Length - the length (height & width) of the crosshair
    9. Rotation (only allowed when the center point coincides with the origin)

    %AMMOIRE*6,0,0,5,0.5,0.5,2,0.1,6,0*%
    """
    print(f"\tcenter point: {x}, {y}")
    print(f"\touter diameter: {outer_dia}")
    print(f"\tring thickness: {ring_thick}")
    print(f"\tdistance between rings: {gap_thick}")
    print(f"\tmax number of rings: {max_rings}")
    print(f"\tcrosshair thickness: {crshr_thick}")
    print(f"\tcrosshair length: {crshr_len}")
    print(f"\trotation: {rotation} degrees")


def process_thermal_primitive(
    x: str,
    y: str,
    outer_dia: str,
    inner_dia: str,
    gap_size: str,
    rotation: str,
) -> None:
    """Output the details of a thermal primitive.

    :param x:               the x center coordinate of the thermal primitive
    :param y:               the y center coordinate of the thermal primitive
    :param outer_dia:       the outer diameter of the thermal primitive
    :param inner_dia:       the inner diameter of the thermal primitive
    :param gap_size:        the size of the gap that interrupts the thermal primitive
    :param rotation:        number of degrees to rotate the thermal primitive

    THERMAL: 7
    --------------------------
    The thermal primitive is a ring (annulus) interrupted by four gaps. Exposure is always on.

    7,X,Y,OD,ID,GT,R

    1. X coordinate of the center of the Thermal
    2. Y coordinate of the center of the Thermal
    3. Outer Diameter of the Thermal
    4. Inner Diameter of the Thermal
    5. Size of the gap that interrupts the Thermal (must be less than the square root of the outer diameter)
    6. Rotation (only allowed when the center point coincides with the origin)

    %AMTHERMAL*7,0,0,8,6,2,0*%
    """
    print(f"\tcenter point: {x}, {y}")
    print(f"\touter diameter: {outer_dia}")
    print(f"\tinner diameter: {inner_dia}")
    print(f"\tpad gap size: {gap_size}")
    print(f"\trotation: {rotation} degrees")


def process_vector_line_primitive(
    exposure: str,
    line_width: str,
    x1: str,
    y1: str,
    x2: str,
    y2: str,
    rotation: str,
) -> None:
    """Output the details of a vector-line primitive.

    :param exposure:        1 for on/dark - will produce an image, 0 for off/clear - will remove an image
    :param line_width:      the width of the vector-line primitive
    :param x1:              the x coordinate of the start of the vector-line primitive
    :param y1:              the y coordinate of the start of the vector-line primitive
    :param x2:              the x coordinate of the end of the vector-line primitive
    :param y2:              the y coordinate of the end of the vector-line primitive
    :param rotation:        number of degrees to rotate the vector-line primitive

    VECTOR LINE: 20
    --------------------------
    A vector line is a rectangle defined by its line width, start and end points. The line ends are rectangular.

    20,E,W,X1,Y1,X2,Y2,R

    1. Exposure
    2. the Line's Width
    3. X1 coordinate of the line start
    4. Y1 coordinate of the line start
    5. X2 coordinate of the line end
    6. Y2 coordinate of the line end
    7. Rotation

    %AMLINE*20,1,0.9,0,0.45,12,0.45,0*%
    """
    print(f"\texposure: {'on' if exposure == '1' else 'off'}")
    print(f"\tline start: {x1}, {y1}")
    print(f"\tline end: {x2}, {y2}")
    print(f"\tline width: {line_width}")
    print(f"\trotation: {rotation} degrees")


def process_center_line_primitive(
    exposure: str,
    line_width: str,
    line_height: str,
    x: str,
    y: str,
    rotation: str,
) -> None:
    """Output the details of a center-line primitive.

    :param exposure:        1 for on/dark - will produce an image, 0 for off/clear - will remove an image
    :param line_width:      the width of the center-line primitive
    :param line_height:     the height of the center-line primitive
    :param x:               the x center coordinate of the center-line primitive
    :param y:               the y center coordinate of the center-line primitive
    :param rotation:        number of degrees to rotate the center-line primitive

    CENTER LINE: 21
    --------------------------
    A vector line is a rectangle defined by its line width, start and end points. The line ends are rectangular.

    21,E,W,H,X,Y,R

    1. Exposure
    2. the Line's Width
    3. the Line's Height
    4. X coordinate of the center of the Line
    5. Y coordinate of the center of the Line
    6. Rotation

    %AMRECTANGLE*21,1,6.8,1.2,3.4,0.6,30*%
    """
    print(f"\texposure: {'on' if exposure == '1' else 'off'}")
    print(f"\tcenter point: {x}, {y}")
    print(f"\tline width: {line_width}")
    print(f"\tline height: {line_height}")
    print(f"\trotation: {rotation} degrees")


if __name__ == "__main__":
    main()
