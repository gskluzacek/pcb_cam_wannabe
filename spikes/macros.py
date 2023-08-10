import re
from typing import Iterable, Iterator

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


def main() -> None:
    macro_00 = "%AMRECTROUNDCORNERS*0 Rectangle with rounded corners. *0 Offsets $4 and $5 are interpreted as the*0 \
    offset of the flash origin from the pad center.*0 First create horizontal rectangle.*21,1,$1,$2-$3-$3,-$4,-$5,0*0 \
    From now on, use width and height half-sizes.*$9=$1/2*$8=$2/2*0 Add top and bottom rectangles.*21,1,$1-$3-$3,$3,\
    -$9+$3-$4,$8-$3-$5,0*21,1,$1-$3-$3,$3,-$9+$3-$4,-$8-$5,0*0 Add circles at the corners.*1,1,$3+$3,-$4+$9-$3,\
    -$5+$8-$3*1,1,$3+$3,-$4-$9+$3,-$5+$8-$3*1,1,$3+$3,-$4-$9+$3,-$5-$8+$3*1,1,$3+$3,-$4+$9-$3,-$5-$8+$3*%"
    macro_01 = "%AMCIRCLE*1,1,1.5,0,0,0*%"
    macro_04 = "%AMTRIANGLE_30*4,1,3,1,-1,1,1,2,1,1,-1,30*%"
    macro_04_2 = "%AMOUTLINE*4,1,4,0.1,0.1,0.5,0.1,0.5,0.5,0.1,0.5,0.1,0.1,0*%"
    macro_05 = "%AMPOLYGON*5,1,8,0,0,8,0*%"
    macro_06 = "%AMMOIRE*6,0,0,5,0.5,0.5,2,0.1,6,0*%"
    macro_07 = "%AMTHERMAL*7,0,0,8,6,2,0*%"
    macro_20 = "%AMLINE*20,1,0.9,0,0.45,12,0.45,0*%"
    macro_21 = "%AMSQUAREWITHHOLE*21,1,10,10,0,0,0*1,0,5,0,0*%"
    macro_21_2 = "%AMRECTANGLE*21,1,6.8,1.2,3.4,0.6,30*%"

    macros = [macro_00, macro_01, macro_04, macro_04_2, macro_05, macro_06, macro_07, macro_20, macro_21, macro_21_2]

    for macro in macros:
        print("")
        print("=" * 100)
        process_macro(macro)


if __name__ == "__main__":
    main()
