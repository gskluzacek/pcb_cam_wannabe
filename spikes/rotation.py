from collections import namedtuple


def process_center_point_offset(ps_x, ps_y, pe_x, pe_y, c_xo, c_yo):
    print(f"staring point: {ps_x:3.6f}, {ps_y:3.6f}")
    print(f"ending point:  {pe_x:3.6f}, {pe_y:3.6f}")
    print(f"center offset: {c_xo:3.6f}, {c_yo:3.6f}\n")

    # calculate the radius, and determine the sign (+ or -) of the center offset (i, j)
    radius, singed_cxo, singed_cyo = get_signed_offsets(c_xo, c_yo, pe_x, pe_y, ps_x, ps_y)

    # use signed center offsets to calculate actual center point
    pc_x, pc_y = ps_x + singed_cxo, ps_y + singed_cyo
    print(
        f"radius:        {radius:3.6f}\n"
        f"offset signed: {singed_cxo:3.6f}, {singed_cyo:3.6f}\n"
        f"center point:  {pc_x:3.6f}, {pc_y:3.6f}"
    )
    print("-" * 100)
    print("")


def get_signed_offsets(c_xo: float, c_yo: float, pe_x: float, pe_y: float, ps_x: float, ps_y: float):
    """
    From an Arc's staring point, ending point, and center offset, calculate its radius and signed offset

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
    # return the x & y offset between 2 points
    return x1 - x2, y1 - y2


def calc_length(x: float, y: float) -> float:
    # TODO: do we need to round?
    # returns the length from the origin for a given vector
    # return round((x * x + y * y) ** 0.5, 6)
    return (x * x + y * y) ** 0.5


def rotate_coords(x1: float, y1: float, x2: float, y2: float) -> tuple[float, float]:
    # TODO: do we need to round?
    # for the given p1 (x1, y1), calculates and returns the point p3 (x3, y3) rotated by vector (x2, y2)
    p2_len = calc_length(x2, y2)
    # print(f"{p2_len = }")
    # x3 = round((x1 * x2 / p2_len) - (y1 * y2 / p2_len), 6)
    # y3 = round((x1 * y2 / p2_len) + (y * x2 / p2_len), 6)
    x3 = (x1 * x2 / p2_len) - (y1 * y2 / p2_len)
    y3 = (x1 * y2 / p2_len) + (y1 * x2 / p2_len)
    return x3, y3


if __name__ == "__main__":
    TestInput = namedtuple("TestInput", ["ps_x", "ps_y", "pe_x", "pe_y", "c_xo", "c_yo"])

    test_data = [
        # TestInput(5, 10, 6.205406, 12.315563, 9.396926, 3.420201),
        # TestInput(-6, 8, -13.515035, 7.671886, 3.5, 6.062178),
        # TestInput(-5, -2, 1.588004, -10.585655, 22.657695, 10.565457),
        # TestInput(-5, -5, 5, 5, 15, 5),
        # TestInput(3.065630, -4.588039, -4.588039, 3.065630, 13.065630, 5.411961),
        # TestInput(-4.588039, 3.065630, 3.065630, -4.588039, 5.411961, 13.065630),
        TestInput(-7.660444, 3.572124, 0, 0, 7.660444, 6.427876),
    ]
    for test in test_data:
        process_center_point_offset(*test)
